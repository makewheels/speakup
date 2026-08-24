import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db.connection import get_db
from routes.review_items import reactivate_review_item, review_kind_filter
from services.auth_tokens import assert_same_user, current_user_id
from services.corrector import correct_text, correct_text_stream
from services.followup_chat import followup_chat_stream
from services.practice_attempts import (
    complete_attempt,
    discard_attempt,
    list_attempts,
    reserve_attempt,
    resolve_attempt,
)
from utils.data_source import normalize_source_type
from utils.id_generator import review_item_id
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/correct", tags=["correct"])


class CorrectRequest(BaseModel):
    userId: str
    practiceId: str
    text: str
    mode: str = "scenario"     # scenario 场景题 / free 自由说（历史缺省按场景题）
    freeTopic: str = ""        # 自由说话题快照（无话题自由说为空）


def _normalize_mode(value: object) -> str:
    return "free" if value == "free" else "scenario"


async def _load_practice(req: CorrectRequest, token_user_id: str) -> dict:
    assert_same_user(req.userId, token_user_id)
    practice = await get_db().practiceSessions.find_one(
        {**id_filter(req.practiceId), "userId": token_user_id}
    )
    if not practice:
        raise HTTPException(404, "练习不存在")
    return practice


async def _correction_context(practice: dict) -> tuple[dict | None, dict | None]:
    """Return the scenario and the latest completed Attempt."""
    scenario = practice.get("scenario")
    attempts = await list_attempts(practice)
    prev = attempts[-1] if attempts else None
    return scenario, prev


def _has_usable_feedback(result: dict) -> bool:
    return bool(
        (result.get("standardAnswer") or "").strip()
        or result.get("score") is not None
        or result.get("gaps")
        or result.get("progress")
    )


async def _save_attempt_and_review(
    req: CorrectRequest, practice: dict, attempt: dict, result: dict
) -> int:
    """Complete one independent Attempt and save opted-in review gaps.

    返回实际新增的复习项数量。
    """
    attempt_id = attempt["attemptId"]
    round_no = int(attempt["round"])
    source_type = normalize_source_type(practice.get("sourceType"))
    # 新笔记改为用户手动选中文字添加。兼容旧字段，但绝不接受/保存纠正模型产出的笔记。
    result["note"] = ""
    result["noteChinese"] = ""
    result.pop("noteReviewItemId", None)
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
        base_filter = {"userId": req.userId, "expression": expression}
        mistake = await get_db().reviewItems.find_one(
            {**base_filter, **review_kind_filter("mistake")}
        )
        if mistake:
            gap["reviewItemId"] = str(mistake["_id"])
            if mistake.get("status") == "retired":
                # 已收纳的表达又说错 → 回到错题本
                await reactivate_review_item(str(mistake["_id"]), now)
            continue

        note = await get_db().reviewItems.find_one(
            {**base_filter, **review_kind_filter("note")}
        )
        if note:
            gap["reviewItemId"] = str(note["_id"])
            if note.get("status") == "retired":
                await reactivate_review_item(str(note["_id"]), now)
            # 只有笔记而没有错题时，沿用历史行为：原记录升级为错题。
            await get_db().reviewItems.update_one(
                id_filter(str(note["_id"])),
                {"$set": {"kind": "mistake", "original": gap.get("original", "")}},
            )
            continue
        rid = review_item_id()
        await get_db().reviewItems.insert_one({
            "_id": rid,
            "userId": req.userId,
            "sourceType": source_type,
            "kind": "mistake",
            "title": gap.get("title", ""),
            "expression": expression,
            "original": gap.get("original", ""),
            "note": gap.get("why", ""),
            "chinese": gap.get("chinese", ""),
            "contextSentence": gap.get("better") or req.text,
            "practiceId": req.practiceId,
            "attemptId": attempt_id,
            "attemptIndex": round_no - 1,
            "status": "active",
            "createdAt": now,
            "nextReviewAt": now,
            "reviewCount": 0,
            "interval": 1,
            "easiness": 2.5,
        })
        gap["reviewItemId"] = rid
        auto_saved += 1

    await complete_attempt(attempt_id, result)
    return auto_saved


@router.post("")
async def correct(req: CorrectRequest, token_user_id: str = Depends(current_user_id)):
    practice = await _load_practice(req, token_user_id)
    scenario, prev = await _correction_context(practice)
    mode = _normalize_mode(practice.get("mode") or req.mode)
    attempt = await reserve_attempt(
        practice,
        transcript=req.text,
        mode=mode,
        free_topic=req.freeTopic or practice.get("freeTopic") or "",
    )
    round_no = attempt["round"]
    link = {
        "sessionId": req.practiceId,
        "attemptId": attempt["attemptId"],
        "userId": req.userId,
        "round": round_no,
        "mode": mode,
        "sourceType": normalize_source_type(practice.get("sourceType")),
    }
    # 自由说的 prompt 模式由场景快照 kind=free 携带（见 corrector.mode_of_scenario）
    try:
        result = await correct_text(req.text, scenario, prev, round_no, link_to=link)
        if not _has_usable_feedback(result):
            raise HTTPException(502, result.get("summary") or "AI 没有返回可用反馈，请重试")
        auto_saved = await _save_attempt_and_review(req, practice, attempt, result)
    except Exception:
        await discard_attempt(attempt["attemptId"])
        raise
    return {
        "practiceId": req.practiceId,
        "attemptId": attempt["attemptId"],
        "autoSaved": auto_saved,
        "round": round_no,
        **result,
    }


@router.post("/stream")
async def correct_stream(req: CorrectRequest, token_user_id: str = Depends(current_user_id)):
    practice = await _load_practice(req, token_user_id)
    scenario, prev = await _correction_context(practice)
    mode = _normalize_mode(practice.get("mode") or req.mode)
    attempt = await reserve_attempt(
        practice,
        transcript=req.text,
        mode=mode,
        free_topic=req.freeTopic or practice.get("freeTopic") or "",
    )
    round_no = attempt["round"]
    link = {
        "sessionId": req.practiceId,
        "attemptId": attempt["attemptId"],
        "userId": req.userId,
        "round": round_no,
        "mode": mode,
        "sourceType": normalize_source_type(practice.get("sourceType")),
    }

    async def generate():
        # 流式推 chunk 让前端显示字数动画，末尾推 done。
        # 流式返空时 correct_text_stream 内部降级非流式，避免生产空 content 导致结果页只剩用户原话。
        completed = False
        try:
            yield f"data: {json.dumps({'type': 'started', 'attemptId': attempt['attemptId'], 'round': round_no})}\n\n"
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
            auto_saved = await _save_attempt_and_review(req, practice, attempt, result)
            completed = True
            done_event = {
                "type": "done",
                "result": result,
                "attemptId": attempt["attemptId"],
                "autoSaved": auto_saved,
                "round": round_no,
            }
            yield f"data: {json.dumps(done_event)}\n\n"
        finally:
            if not completed:
                await discard_attempt(attempt["attemptId"])

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
    attemptId: str = ""
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

    attempt = await resolve_attempt(
        practice,
        attempt_id=req.attemptId,
        attempt_index=req.attemptIndex,
    )
    if not attempt:
        raise HTTPException(400, "还没有反馈可追问")
    idx = int(attempt.get("round") or 1) - 1
    attempt_id = attempt.get("attemptId", "")
    scenario = practice.get("scenario")
    history = attempt.get("chat", [])
    link = {
        "sessionId": req.practiceId,
        "userId": req.userId,
        "attemptId": attempt_id,
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
            messages = [
                    {"role": "user", "content": req.question, "createdAt": now},
                    {"role": "assistant", "content": full, "createdAt": now},
                ]
            updated = await get_db().practiceAttempts.update_one(
                {**id_filter(attempt_id), "practiceId": req.practiceId},
                {"$push": {"chat": {"$each": messages}}},
            )
            if updated.matched_count == 0:
                # One-release compatibility while embedded Attempts are migrated.
                await get_db().practiceSessions.update_one(
                    id_filter(req.practiceId),
                    {"$push": {f"attempts.{idx}.chat": {"$each": messages}}},
                )
            yield f"data: {json.dumps({'type': 'done', 'text': full})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
