from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal

from db.connection import get_db
from services.auth_tokens import current_user_id
from services.storage_paths import PracticeAssetContext, speech_key
from services.tts import speak_url, speech_asset
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/tts", tags=["tts"])


class TtsRequest(BaseModel):
    text: str
    practiceId: str | None = None
    attemptIndex: int = -1
    purpose: Literal[
        "correction",
        "example",
        "other",
        "pronunciation-target",
        "review",
        "standard-answer",
    ] = "other"


@router.post("")
async def tts(req: TtsRequest, token_user_id: str = Depends(current_user_id)):
    """文本 → 朗读音频 OSS 签名 URL（按 practiceId 挂 session 下，命中缓存不花钱）。"""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "text is empty")
    if len(text) > 600:
        raise HTTPException(413, "text too long")
    storage_key = None
    practice = None
    attempt_index = -1
    if req.practiceId:
        practice = await get_db().practiceSessions.find_one(
            {**id_filter(req.practiceId), "userId": token_user_id},
            {"_id": 1, "userId": 1, "createdAt": 1, "attempts": 1},
        )
        if not practice:
            raise HTTPException(404, "练习不存在")
        attempts = practice.get("attempts", [])
        attempt_index = req.attemptIndex if 0 <= req.attemptIndex < len(attempts) else len(attempts) - 1
        if attempt_index < 0:
            raise HTTPException(409, "本练习还没有可归档朗读音频的轮次")
        audio_id, extension, content_type = speech_asset(text)
        context = PracticeAssetContext(
            user_id=practice["userId"],
            created_at=practice["createdAt"],
            practice_id=req.practiceId,
            attempt_index=attempt_index,
        )
        storage_key = speech_key(context, req.purpose, audio_id, extension)
    try:
        url = await speak_url(text, storage_key=storage_key)
    except Exception as exc:
        raise HTTPException(500, f"TTS failed: {exc}") from exc
    if practice and storage_key:
        asset = {
            "id": audio_id,
            "key": storage_key,
            "purpose": req.purpose,
            "format": extension,
            "contentType": content_type,
        }
        await get_db().practiceSessions.update_one(
            id_filter(req.practiceId),
            {"$addToSet": {f"attempts.{attempt_index}.speechAssets": asset}},
        )
    return {"url": url}
