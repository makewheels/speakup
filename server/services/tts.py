"""文本转语音：火山 openspeech Agent Plan 合成英文朗读。

朗读音频存 `practiceSessions/{practiceId}/tts/{hash}.mp3`，挂在 session 下。
session 内重听同一段仍走 OSS 缓存（按 hash 去重）。
"""

import asyncio
import base64
import hashlib
import json
import uuid

import httpx

from config import (
    TTS_MODEL,
    TTS_RESOURCE_ID,
    TTS_VOICE,
    VOICE_API_KEY,
    VOICE_APP_KEY,
    VOICE_TTS_URL,
)
from services.oss_storage import exists, get_url, upload_bytes


def _cache_key(text: str, practice_id: str | None = None) -> str:
    digest = hashlib.sha1(f"{TTS_RESOURCE_ID}:{TTS_MODEL}:{TTS_VOICE}:{text}".encode()).hexdigest()
    if practice_id:
        return f"practiceSessions/{practice_id}/tts/{digest}.mp3"
    return f"tts/{digest}.mp3"


def _looks_like_audio(data: bytes) -> bool:
    return data.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"))


def _audio_from_json(value: dict) -> bytes:
    code = value.get("code")
    if code not in (None, 0, 20000000):
        raise RuntimeError(f"TTS failed: {value}")

    candidates = [
        value.get("data"),
        value.get("audio"),
        (value.get("response") or {}).get("data") if isinstance(value.get("response"), dict) else None,
        (value.get("result") or {}).get("data") if isinstance(value.get("result"), dict) else None,
    ]
    for item in candidates:
        if not isinstance(item, str) or not item:
            continue
        try:
            audio = base64.b64decode(item, validate=True)
        except Exception:
            continue
        if audio:
            return audio
    return b""


def _parse_tts_response(resp: httpx.Response) -> bytes:
    data = resp.content
    content_type = resp.headers.get("content-type", "")
    if "audio/" in content_type or _looks_like_audio(data):
        return data

    chunks: list[bytes] = []
    text = data.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line.removeprefix("data:").strip()
        if line == "[DONE]":
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        chunk = _audio_from_json(event)
        if chunk:
            chunks.append(chunk)

    if not chunks:
        raise RuntimeError(f"TTS 无音频返回: {text[:500]}")
    return b"".join(chunks)


def _synthesize(text: str) -> bytes:
    request_id = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {VOICE_API_KEY}",
        "X-Api-Key": VOICE_API_KEY,
        "X-Api-App-Key": VOICE_APP_KEY,
        "X-Api-Access-Key": VOICE_API_KEY,
        "X-Api-Resource-Id": TTS_RESOURCE_ID,
        "X-Api-Request-Id": request_id,
        "Content-Type": "application/json",
    }
    payload = {
        "user": {"uid": "speakup"},
        "req_params": {
            "text": text,
            "speaker": TTS_VOICE,
            "audio_params": {"format": "mp3", "sample_rate": 24000},
        },
    }
    with httpx.Client(timeout=90.0) as c:
        resp = c.post(VOICE_TTS_URL, headers=headers, json=payload)
    resp.raise_for_status()
    audio = _parse_tts_response(resp)
    if not audio:
        raise RuntimeError("TTS 无音频返回")
    return audio


async def speak_url(text: str, practice_id: str | None = None) -> str:
    """返回这句话朗读音频的 OSS 签名 URL。命中缓存直接返回，否则合成后存 OSS。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")
    key = _cache_key(text, practice_id)
    if not await asyncio.to_thread(exists, key):
        audio = await asyncio.to_thread(_synthesize, text)
        await asyncio.to_thread(upload_bytes, key, audio, "audio/mpeg")
    return await asyncio.to_thread(get_url, key)
