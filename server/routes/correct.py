import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from services.corrector import correct_text, correct_text_stream
from services.followup_chat import followup_chat_stream
from utils.data_source import normalize_source_type
from utils.id_generator import review_item_id
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/correct", tags=["correct"])


class CorrectRequest(BaseModel):
    userId: str
    practiceId: str
    text: str


async def _load_practice(req: CorrectRequest, token_user_id: str) -> dict:
    assert_same_user(req.userId, token_user_id)
    practice = await get_db().practiceSessions.find_one(
        {**id_filter(req.practiceId), "userId": token_user_id}
    )
    if not practice:
        raise HTTPException(404, "练习不存在")
    return practice


def _round_context(practice: dict) -> tuple[dict | None, dict | None, int]:
    """从练习取（场景, 上一轮 attempt, 本轮轮次）。轮次从 1 开始，不封顶（同一题可无限重说）。"""
    scenario = practice.get("scenario")
    attempts = practice.get("attempts", [])
    round_no = len(attempts) + 1
    prev = attempts[-1] if attempts else None
    return scenario, prev, round_no


def _has_usable_feedback(result: dict) -> bool:
    return bool((result.get("nativeVersion") or "").strip() or result.get("gaps"))


async def _save_attempt_and_review(
    req: CorrectRequest, result: dict, round_no: int, source_type: str
) -> int:
    """写入练习的 attempts，并自动把 saveToReview=true 的 gap 存进 reviewItems（错题/复习项）。
    返回实际新增的复习项数量。
    """
    # 先自动收录 saveToReview 的 gap，把 reviewItemId 回写到 gap 上，
    # 再写入 attempt —— 这样存进库的 attempt 和回给前端的 result 都带 id。
    auto_saved = 0
    now = datetime.now(timezone.utc)
    for gap in result.get("gaps", []):
        if not gap.get("saveToReview"):
            continue
        expression = gap.get("better", "").strip()
        if not expression:
            continue
        existing = await get_db().reviewItems.find_one({"userId": req.userId, "expression": expression})
        if existing:
            gap["reviewItemId"] = str(existing["_id"])
            continue
        rid = review_item_id()
        await get_db().reviewItems.insert_one({
            "_id": rid,
            "userId": req.userId,
            "sourceType": source_type,
            "title": gap.get("title", ""),
            "expression": expression,
            "original": gap.get("original", ""),
            "note": gap.get("why", ""),
            "contextSentence": result.get("nativeVersion", ""),
            "practiceId": req.practiceId,
            "createdAt": now,
            "nextReviewAt": now,
            "reviewCount": 0,
            "interval": 1,
            "easiness": 2.5,
        })
        gap["reviewItemId"] = rid
        auto_saved += 1

    attempt = {
        "transcript": req.text,
        "round": round_no,
        "summary": result["summary"],
        "nativeVersion": result["nativeVersion"],
        "standardAnswer": result.get("standardAnswer", ""),
        "score": result.get("score"),
        "gaps": result["gaps"],
        "progress": result.get("progress"),
        "createdAt": now,
    }
    await get_db().practiceSessions.update_one(
        id_filter(req.practiceId),
        {"$push": {"attempts": attempt}},
    )
    return auto_saved


@router.post("")
async def correct(req: CorrectRequest, token_user_id: str = Depends(current_user_id)):
    practice = await _load_practice(req, token_user_id)
    scenario, prev, round_no = _round_context(practice)
    source_type = normalize_source_type(practice.get("sourceType"))
    link = {
        "sessionId": req.practiceId,
        "userId": req.userId,
        "round": round_no,
        "sourceType": source_type,
    }
    result = await correct_text(req.text, scenario, prev, round_no, link_to=link)
    if not _has_usable_feedback(result):
        raise HTTPException(502, result.get("summary") or "AI 没有返回可用反馈，请重试")
    auto_saved = await _save_attempt_and_review(req, result, round_no, source_type)
    return {"practiceId": req.practiceId, "autoSaved": auto_saved, "round": round_no, **result}


@router.post("/stream")
async def correct_stream(req: CorrectRequest, token_user_id: str = Depends(current_user_id)):
    practice = await _load_practice(req, token_user_id)
    scenario, prev, round_no = _round_context(practice)
    source_type = normalize_source_type(practice.get("sourceType"))
    link = {
        "sessionId": req.practiceId,
        "userId": req.userId,
        "round": round_no,
        "sourceType": source_type,
    }

    async def generate():
        # 流式推 chunk 让前端显示字数动画，末尾推 done。
        # 流式返空时 correct_text_stream 内部降级非流式，避免生产空 content 导致结果页只剩用户原话。
        result = None
        async for event_type, data in correct_text_stream(
            req.text, scenario, prev, round_no, link_to=link
        ):
            if event_type == "chunk":
                yield f"data: {json.dumps({'type': 'chunk', 'text': data['text']})}\n\n"
            elif event_type == "usage":
                yield f"data: {json.dumps({'type': 'usage', **data})}\n\n"
            elif event_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': data['message']})}\n\n"
                return
            elif event_type == "done":
                result = data
        if not result or not _has_usable_feedback(result):
            message = (result or {}).get('summary') or 'AI 没有返回可用反馈，请重试'
            yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
            return
        auto_saved = await _save_attempt_and_review(req, result, round_no, source_type)
        yield f"data: {json.dumps({'type': 'done', 'result': result, 'autoSaved': auto_saved, 'round': round_no})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class ChatRequest(BaseModel):
    userId: str
    practiceId: str
    attemptIndex: int = -1  # 默认对最后一次 attempt 的反馈追问
    question: str


@router.post("/chat/stream")
async def correct_chat_stream(req: ChatRequest, token_user_id: str = Depends(current_user_id)):  # noqa: C901
    """用户拿到反馈后，基于本次练习上下文继续追问 AI（SSE 纯文本流）。
    把问答历史存进对应 attempt 的 chat 数组，刷新/历史页可回看。
    """
    if not req.question or not req.question.strip():
        raise HTTPException(400, "问题不能为空")

    assert_same_user(req.userId, token_user_id)
    practice = await get_db().practiceSessions.find_one(
        {**id_filter(req.practiceId), "userId": token_user_id}
    )
    if not practice:
        raise HTTPException(404, "练习不存在")

    attempts = practice.get("attempts", [])
    if not attempts:
        raise HTTPException(400, "还没有反馈可追问")
    idx = req.attemptIndex if 0 <= req.attemptIndex < len(attempts) else len(attempts) - 1
    attempt = attempts[idx]
    scenario = practice.get("scenario")
    history = attempt.get("chat", [])
    link = {
        "sessionId": req.practiceId,
        "userId": req.userId,
        "attemptIndex": idx,
        "sourceType": normalize_source_type(practice.get("sourceType")),
    }

    async def generate():
        full = ""
        errored = False
        async for event_type, data in followup_chat_stream(
            scenario, attempt, history, req.question, link_to=link
        ):
            if event_type == "chunk":
                full += data["text"]
                yield f"data: {json.dumps({'type': 'chunk', 'text': data['text']})}\n\n"
            elif event_type == "usage":
                yield f"data: {json.dumps({'type': 'usage', **data})}\n\n"
            elif event_type == "error":
                errored = True
                yield f"data: {json.dumps({'type': 'error', 'message': data['message']})}\n\n"
                return
            elif event_type == "done":
                full = data["text"]

        if not errored and full:
            now = datetime.now(timezone.utc)
            await get_db().practiceSessions.update_one(
                id_filter(req.practiceId),
                {"$push": {f"attempts.{idx}.chat": {"$each": [
                    {"role": "user", "content": req.question, "createdAt": now},
                    {"role": "assistant", "content": full, "createdAt": now},
                ]}}},
            )
            yield f"data: {json.dumps({'type': 'done', 'text': full})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
