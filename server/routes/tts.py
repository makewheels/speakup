from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import current_user_id
from services.tts import speak_url
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/tts", tags=["tts"])


class TtsRequest(BaseModel):
    text: str
    practiceId: str | None = None


@router.post("")
async def tts(req: TtsRequest, token_user_id: str = Depends(current_user_id)):
    """文本 → 朗读音频 OSS 签名 URL（按 practiceId 挂 session 下，命中缓存不花钱）。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "text is empty")
    if len(text) > 600:
        raise HTTPException(413, "text too long")
    if req.practiceId:
        practice = await get_db().practiceSessions.find_one(
            {**id_filter(req.practiceId), "userId": token_user_id},
            {"_id": 1},
        )
        if not practice:
            raise HTTPException(404, "练习不存在")
    try:
        url = await speak_url(text, practice_id=req.practiceId)
    except Exception as exc:
        raise HTTPException(500, f"TTS failed: {exc}") from exc
    return {"url": url}
