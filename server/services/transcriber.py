"""音频转写服务

调用 DashScope qwen3-asr-flash（OpenAI 兼容 audio 接口）。
前端浏览器录音格式不一致：iOS 录 m4a/mp4、Android 录 webm/ogg。
qwen3-asr 直接支持 wav/mp3/m4a/flac/aac，不支持 webm，
所以服务器先用 ffmpeg 统一转成 mp3 再送出去。
"""
import asyncio
import base64
import logging
import tempfile
from pathlib import Path

from openai import AsyncOpenAI

from config import ASR_MODEL, DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=DASHSCOPE_API_KEY,
            base_url=f"{DASHSCOPE_BASE_URL}/compatible-mode/v1",
            timeout=60.0,
        )
    return _client


async def _to_mp3(audio_bytes: bytes, suffix: str) -> bytes:
    """ffmpeg 转 mp3，统一编码避免 webm/m4a 兼容问题。"""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(audio_bytes)
        src_path = src.name
    dst_path = src_path + ".mp3"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", src_path,
            "-ar", "16000", "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "64k",
            dst_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode()[:200]}")
        return Path(dst_path).read_bytes()
    finally:
        Path(src_path).unlink(missing_ok=True)
        Path(dst_path).unlink(missing_ok=True)


async def transcribe(audio_bytes: bytes, content_type: str = "") -> str:
    """把任意主流浏览器录音转成英文文字。"""
    suffix = ".webm"
    if "mp4" in content_type or "m4a" in content_type or "aac" in content_type:
        suffix = ".m4a"
    elif "ogg" in content_type:
        suffix = ".ogg"
    elif "wav" in content_type:
        suffix = ".wav"

    mp3 = await _to_mp3(audio_bytes, suffix)
    b64 = base64.b64encode(mp3).decode()

    client = _get_client()
    resp = await client.chat.completions.create(
        model=ASR_MODEL,
        messages=[
            {
                "role": "system",
                "content": [{"type": "text", "text": ""}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": f"data:;base64,{b64}", "format": "mp3"},
                    }
                ],
            },
        ],
        extra_body={"asr_options": {"language": "en", "enable_lid": False, "enable_itn": True}},
    )
    text = (resp.choices[0].message.content or "").strip()
    logger.info("ASR transcribed %d bytes -> %d chars", len(audio_bytes), len(text))
    return text
