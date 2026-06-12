import asyncio
import json
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db.connection import get_db
from services.corrector import MAX_ROUNDS, correct_text, correct_text_stream
from services.scenario_service import generate_custom_scenario

router = APIRouter(prefix="/api/correct", tags=["correct"])

logger = logging.getLogger(__name__)


class CorrectRequest(BaseModel):
    userId: str
    sessionId: str
    text: str


async def _load_session(req: CorrectRequest) -> dict:
    try:
        session = await get_db().sessions.find_one(
            {"_id": ObjectId(req.sessionId), "userId": req.userId}
        )
    except Exception:
        raise HTTPException(404, "会话不存在")
    if not session:
        raise HTTPException(404, "会话不存在")
    return session


def _round_context(session: dict) -> tuple[dict | None, dict | None, int]:
    """从 session 取（场景, 上一轮 attempt, 本轮轮次）。轮次从 1 开始，封顶 MAX_ROUNDS。"""
    scenario = session.get("scenario")
    attempts = session.get("attempts", [])
    round_no = min(len(attempts) + 1, MAX_ROUNDS)
    prev = attempts[-1] if attempts else None
    return scenario, prev, round_no


async def _save_attempt_and_vocabulary(req: CorrectRequest, result: dict, round_no: int) -> int:
    """写入 session.attempts，并自动保存 saveToReview=true 的 gap 到 vocabulary。
    返回实际新增的复习项数量。
    """
    attempt = {
        "transcript": req.text,
        "round": round_no,
        "summary": result["summary"],
        "nativeVersion": result["nativeVersion"],
        "gaps": result["gaps"],
        "progress": result.get("progress"),
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
            "title": gap.get("title", ""),
            "word": word,
            "original": gap.get("original", ""),
            "note": gap.get("why", ""),
            "contextSentence": result.get("nativeVersion", ""),
            "sessionId": req.sessionId,
            "imageUrl": "",
            "createdAt": now,
            "nextReviewAt": now,
            "reviewCount": 0,
            "interval": 1,
            "easiness": 2.5,
        })
        auto_saved += 1
    return auto_saved


def _schedule_custom_scenario(user_id: str) -> None:
    """因材施教：后台静默生成定制题（出错 → 反向出题），失败只记日志。"""
    async def _run():
        try:
            doc = await generate_custom_scenario(user_id)
            if doc:
                logger.info("custom scenario generated for %s: %s", user_id, doc["slug"])
        except Exception as e:
            logger.warning("custom scenario generation failed for %s: %s", user_id, e)

    asyncio.create_task(_run())


@router.post("")
async def correct(req: CorrectRequest):
    session = await _load_session(req)
    scenario, prev, round_no = _round_context(session)
    result = await correct_text(req.text, scenario, prev, round_no)
    auto_saved = await _save_attempt_and_vocabulary(req, result, round_no)
    if auto_saved:
        _schedule_custom_scenario(req.userId)
    return {"sessionId": req.sessionId, "autoSaved": auto_saved, "round": round_no, **result}


@router.post("/stream")
async def correct_stream(req: CorrectRequest):
    session = await _load_session(req)
    scenario, prev, round_no = _round_context(session)

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
            auto_saved = await _save_attempt_and_vocabulary(req, full_result, round_no)
            if auto_saved:
                _schedule_custom_scenario(req.userId)
            yield f"data: {json.dumps({'type': 'done', 'result': full_result, 'autoSaved': auto_saved, 'round': round_no})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
