import logging
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from services.auth_tokens import assert_same_user, current_user_id
from services.transcriber import transcribe

router = APIRouter(prefix="/api/transcribe", tags=["transcribe"])
logger = logging.getLogger(__name__)


@router.post("")
async def transcribe_audio(
    audio: UploadFile = File(...),
    userId: str = Form(...),
    token_user_id: str = Depends(current_user_id),
):
    """上传录音返回转写文本（iOS / 不支持 Web Speech API 的浏览器走这条路）。"""
    assert_same_user(userId, token_user_id)
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "audio is empty")
    if len(audio_bytes) > 30 * 1024 * 1024:
        raise HTTPException(413, "audio too large (>30MB)")
    started = time.monotonic()
    try:
        text = await transcribe(audio_bytes, audio.content_type or "")
    except Exception as exc:
        logger.exception(
            "ASR failed content_type=%s bytes=%s duration_ms=%s",
            audio.content_type,
            len(audio_bytes),
            int((time.monotonic() - started) * 1000),
        )
        raise HTTPException(500, f"ASR failed: {exc}") from exc
    logger.info(
        "ASR done content_type=%s bytes=%s chars=%s duration_ms=%s",
        audio.content_type,
        len(audio_bytes),
        len(text),
        int((time.monotonic() - started) * 1000),
    )
    return {"text": text}
