from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from bson import ObjectId
from db.connection import get_db
from services.corrector import correct_text

router = APIRouter(prefix="/api/correct", tags=["correct"])


class CorrectRequest(BaseModel):
    userId: str
    sessionId: str
    text: str
    imageUrl: str = ""


@router.post("")
async def correct(req: CorrectRequest):
    try:
        session = await get_db().sessions.find_one({"_id": ObjectId(req.sessionId), "userId": req.userId})
    except Exception:
        raise HTTPException(404, "会话不存在")
    if not session:
        raise HTTPException(404, "会话不存在")

    result = await correct_text(req.text, req.imageUrl)

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

    return {"sessionId": req.sessionId, **result}
