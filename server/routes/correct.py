import json
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db.connection import get_db
from services.corrector import correct_text, correct_text_stream

router = APIRouter(prefix="/api/correct", tags=["correct"])


class CorrectRequest(BaseModel):
    userId: str
    sessionId: str
    text: str
    imageUrl: str = ""


async def _save_attempt_and_vocabulary(req: CorrectRequest, result: dict) -> int:
    """写入 session.attempts，并自动保存 saveToReview=true 的 gap 到 vocabulary。
    返回实际新增的复习项数量。
    """
    attempt = {
        "transcript": req.text,
        "summary": result["summary"],
        "nativeVersion": result["nativeVersion"],
        "gaps": result["gaps"],
        "createdAt": datetime.now(timezone.utc),
    }
    await get_db().sessions.update_one(
        {"_id": ObjectId(req.sessionId)},
        {"$push": {"attempts": attempt}},
    )

    auto_saved = 0
    now = datetime.now(timezone.utc)
    for gap in result.get("gaps", []):
        if not gap.get("saveToReview"):
            continue
        word = gap.get("better", "").strip()
        if not word:
            continue
        existing = await get_db().vocabulary.find_one({"userId": req.userId, "word": word})
        if existing:
            continue
        await get_db().vocabulary.insert_one({
            "userId": req.userId,
            "word": word,
            "original": gap.get("original", ""),
            "note": gap.get("why", ""),
            "contextSentence": result.get("nativeVersion", ""),
            "sessionId": req.sessionId,
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
    try:
        session = await get_db().sessions.find_one(
            {"_id": ObjectId(req.sessionId), "userId": req.userId}
        )
    except Exception:
        raise HTTPException(404, "会话不存在")
    if not session:
        raise HTTPException(404, "会话不存在")

    result = await correct_text(req.text, req.imageUrl)
    auto_saved = await _save_attempt_and_vocabulary(req, result)
    return {"sessionId": req.sessionId, "autoSaved": auto_saved, **result}


@router.post("/stream")
async def correct_stream(req: CorrectRequest):
    try:
        session = await get_db().sessions.find_one(
            {"_id": ObjectId(req.sessionId), "userId": req.userId}
        )
    except Exception:
        raise HTTPException(404, "会话不存在")
    if not session:
        raise HTTPException(404, "会话不存在")

    async def generate():
        full_result = None
        async for event_type, data in correct_text_stream(req.text, req.imageUrl):
            if event_type == "chunk":
                yield f"data: {json.dumps({'type': 'chunk', 'text': data['text']})}\n\n"
            elif event_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': data['message']})}\n\n"
                return
            elif event_type == "done":
                full_result = data

        if full_result:
            auto_saved = await _save_attempt_and_vocabulary(req, full_result)
            yield f"data: {json.dumps({'type': 'done', 'result': full_result, 'autoSaved': auto_saved})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
