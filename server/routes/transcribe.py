from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.transcriber import transcribe

router = APIRouter(prefix="/api/transcribe", tags=["transcribe"])


@router.post("")
async def transcribe_audio(
    audio: UploadFile = File(...),
    userId: str = Form(...),
):
    """上传录音返回转写文本（iOS / 不支持 Web Speech API 的浏览器走这条路）。"""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(400, "audio is empty")
    if len(audio_bytes) > 30 * 1024 * 1024:
        raise HTTPException(413, "audio too large (>30MB)")
    try:
        text = await transcribe(audio_bytes, audio.content_type or "")
    except Exception as exc:
        raise HTTPException(500, f"ASR failed: {exc}") from exc
    return {"text": text}
