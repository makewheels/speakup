import json
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db.connection import get_db
from services.corrector import MAX_ROUNDS, correct_text, correct_text_stream

router = APIRouter(prefix="/api/correct", tags=["correct"])


class CorrectRequest(BaseModel):
    userId: str
    practiceId: str
    text: str


async def _load_practice(req: CorrectRequest) -> dict:
    try:
        practice = await get_db().practiceSessions.find_one(
            {"_id": ObjectId(req.practiceId), "userId": req.userId}
        )
    except Exception:
        raise HTTPException(404, "练习不存在")
    if not practice:
        raise HTTPException(404, "练习不存在")
    return practice


def _round_context(practice: dict) -> tuple[dict | None, dict | None, int]:
    """从练习取（场景, 上一轮 attempt, 本轮轮次）。轮次从 1 开始，封顶 MAX_ROUNDS。"""
    scenario = practice.get("scenario")
    attempts = practice.get("attempts", [])
    round_no = min(len(attempts) + 1, MAX_ROUNDS)
    prev = attempts[-1] if attempts else None
    return scenario, prev, round_no


async def _save_attempt_and_review(req: CorrectRequest, result: dict, round_no: int) -> int:
    """写入练习的 attempts，并自动把 saveToReview=true 的 gap 存进 reviewItems（错题/复习项）。
    返回实际新增的复习项数量。
    """
    attempt = {
        "transcript": req.text,
        "round": round_no,
        "summary": result["summary"],
        "nativeVersion": result["nativeVersion"],
        "score": result.get("score"),
        "gaps": result["gaps"],
        "progress": result.get("progress"),
        "createdAt": datetime.now(timezone.utc),
    }
    await get_db().practiceSessions.update_one(
        {"_id": ObjectId(req.practiceId)},
        {"$push": {"attempts": attempt}},
    )

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
            continue
        await get_db().reviewItems.insert_one({
            "userId": req.userId,
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
        auto_saved += 1
    return auto_saved


@router.post("")
async def correct(req: CorrectRequest):
    practice = await _load_practice(req)
    scenario, prev, round_no = _round_context(practice)
    result = await correct_text(req.text, scenario, prev, round_no)
    auto_saved = await _save_attempt_and_review(req, result, round_no)
    return {"practiceId": req.practiceId, "autoSaved": auto_saved, "round": round_no, **result}


@router.post("/stream")
async def correct_stream(req: CorrectRequest):
    practice = await _load_practice(req)
    scenario, prev, round_no = _round_context(practice)

    async def generate():
        full_result = None
        async for event_type, data in correct_text_stream(req.text, scenario, prev, round_no):
            if event_type == "chunk":
                yield f"data: {json.dumps({'type': 'chunk', 'text': data['text']})}\n\n"
            elif event_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': data['message']})}\n\n"
                return
            elif event_type == "done":
                full_result = data

        if full_result:
            auto_saved = await _save_attempt_and_review(req, full_result, round_no)
            yield f"data: {json.dumps({'type': 'done', 'result': full_result, 'autoSaved': auto_saved, 'round': round_no})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
