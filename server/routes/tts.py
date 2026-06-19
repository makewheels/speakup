from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.tts import speak_url

router = APIRouter(prefix="/api/tts", tags=["tts"])


class TtsRequest(BaseModel):
    text: str
    practiceId: str | None = None


@router.post("")
async def tts(req: TtsRequest):
    """文本 → 朗读音频 OSS 签名 URL（按 practiceId 挂 session 下，命中缓存不花钱）。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "text is empty")
    if len(text) > 600:
        raise HTTPException(413, "text too long")
    try:
        url = await speak_url(text, practice_id=req.practiceId)
    except Exception as exc:
        raise HTTPException(500, f"TTS failed: {exc}") from exc
    return {"url": url}
