"""音频转写服务：火山 openspeech Agent Plan Seed-ASR。

前端浏览器录音格式不一致：iOS 录 m4a/mp4、Android 录 webm/ogg。
服务器先用 ffmpeg 统一转成 16k mono raw PCM，再送 ASR WebSocket 接口。
"""

import asyncio
import gzip
import json
import logging
import tempfile
import uuid
from pathlib import Path

import websockets

from config import ASR_MODEL, ASR_RESOURCE_ID, VOICE_API_KEY, VOICE_APP_KEY, VOICE_ASR_URL

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = 0x1
_HEADER_SIZE = 0x1
_MSG_FULL_CLIENT = 0x1
_MSG_AUDIO_ONLY = 0x2
_MSG_FULL_SERVER = 0x9
_MSG_ERROR = 0xF
_FLAG_NONE = 0x0
_FLAG_LAST_NO_SEQUENCE = 0x2
_SER_JSON = 0x1
_SER_NONE = 0x0
_COMP_NONE = 0x0
_COMP_GZIP = 0x1
_AUDIO_CHUNK_BYTES = 256 * 1024


def _header(message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    return bytes([
        (_PROTOCOL_VERSION << 4) | _HEADER_SIZE,
        (message_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])


def _frame(message_type: int, flags: int, serialization: int, payload: bytes) -> bytes:
    compressed = gzip.compress(payload)
    return (
        _header(message_type, flags, serialization, _COMP_GZIP)
        + len(compressed).to_bytes(4, "big", signed=False)
        + compressed
    )


def _full_client_request() -> bytes:
    payload = {
        "user": {"uid": "speakup"},
        "audio": {
            "format": "pcm",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "language": "en-US",
        },
        "request": {
            "model_name": ASR_MODEL,
            "enable_itn": True,
            "enable_punc": True,
            "enable_lid": False,
            "result_type": "full",
        },
    }
    return _frame(_MSG_FULL_CLIENT, _FLAG_NONE, _SER_JSON, json.dumps(payload).encode())


def _audio_request(audio: bytes, *, last: bool) -> bytes:
    return _frame(
        _MSG_AUDIO_ONLY,
        _FLAG_LAST_NO_SEQUENCE if last else _FLAG_NONE,
        _SER_NONE,
        audio,
    )


def _audio_chunks(audio: bytes) -> list[bytes]:
    return [audio[i:i + _AUDIO_CHUNK_BYTES] for i in range(0, len(audio), _AUDIO_CHUNK_BYTES)] or [b""]


def _parse_response(message: bytes | str) -> tuple[dict | None, bool]:
    if isinstance(message, str):
        return json.loads(message), False
    if len(message) < 8:
        raise RuntimeError(f"ASR invalid frame length: {len(message)}")

    header_size = (message[0] & 0x0F) * 4
    message_type = (message[1] & 0xF0) >> 4
    flags = message[1] & 0x0F
    compression = message[2] & 0x0F
    offset = header_size

    if message_type == _MSG_ERROR:
        code = int.from_bytes(message[offset:offset + 4], "big", signed=False)
        offset += 4
        size = int.from_bytes(message[offset:offset + 4], "big", signed=False)
        offset += 4
        detail = message[offset:offset + size].decode("utf-8", errors="replace")
        raise RuntimeError(f"ASR error {code}: {detail}")

    if message_type != _MSG_FULL_SERVER:
        return None, False

    if flags in (0x1, 0x3):
        offset += 4  # sequence
    size = int.from_bytes(message[offset:offset + 4], "big", signed=False)
    offset += 4
    payload = message[offset:offset + size]
    if compression == _COMP_GZIP:
        payload = gzip.decompress(payload)
    elif compression != _COMP_NONE:
        raise RuntimeError(f"ASR unsupported compression: {compression}")

    return json.loads(payload.decode("utf-8")), flags == 0x3


def _text_from_response(data: dict) -> str:
    result = data.get("result") or {}
    if isinstance(result, dict):
        return (result.get("text") or "").strip()
    if isinstance(result, list):
        texts = [str(item.get("text", "")).strip() for item in result if isinstance(item, dict)]
        return " ".join(t for t in texts if t).strip()
    return ""


async def _to_pcm(audio_bytes: bytes, suffix: str) -> bytes:
    """ffmpeg 转 16k mono s16le PCM，统一编码避免 webm/m4a 兼容问题。"""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(audio_bytes)
        src_path = src.name
    dst_path = src_path + ".pcm"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", src_path,
            "-ar", "16000", "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le",
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

    pcm = await _to_pcm(audio_bytes, suffix)
    headers = {
        "Authorization": f"Bearer {VOICE_API_KEY}",
        "X-Api-Key": VOICE_API_KEY,
        "X-Api-App-Key": VOICE_APP_KEY,
        "X-Api-Access-Key": VOICE_API_KEY,
        "X-Api-Resource-Id": ASR_RESOURCE_ID,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }

    text = ""
    async with websockets.connect(
        VOICE_ASR_URL,
        additional_headers=headers,
        compression=None,
        proxy=None,
        open_timeout=15,
        ping_interval=None,
        max_size=8 * 1024 * 1024,
    ) as ws:
        await ws.send(_full_client_request())
        data, _ = _parse_response(await asyncio.wait_for(ws.recv(), timeout=20))
        if data:
            text = _text_from_response(data) or text

        chunks = _audio_chunks(pcm)
        for index, chunk in enumerate(chunks):
            await ws.send(_audio_request(chunk, last=index == len(chunks) - 1))

        while True:
            data, final = _parse_response(await asyncio.wait_for(ws.recv(), timeout=60))
            if data:
                text = _text_from_response(data) or text
            if final:
                break

    logger.info("ASR transcribed %d bytes -> %d chars", len(audio_bytes), len(text))
    return text
