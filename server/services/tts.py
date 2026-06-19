"""文本转语音：DashScope CosyVoice 合成英文朗读。

朗读音频存 `practiceSessions/{practiceId}/tts/{hash}.mp3`，挂在 session 下——
LLM 个性化生成的 nativeVersion / gap.better 几乎不会跨 session 撞同一句，
全局 tts/ 缓存命中率约等于 0；挂 session 下让所有资源结构对齐
（题目图在 scenarios/，session 内的录音 + 朗读都在 practiceSessions/ 下）。
session 内重听同一段仍走 OSS 缓存（按 hash 去重）。
"""
import asyncio
import hashlib
import os

import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer

from config import DASHSCOPE_API_KEY
from services.oss_storage import exists, get_url, upload_bytes

TTS_MODEL = os.getenv("TTS_MODEL", "cosyvoice-v2")
TTS_VOICE = os.getenv("TTS_VOICE", "longxiaochun_v2")


def _cache_key(text: str, practice_id: str | None = None) -> str:
    digest = hashlib.sha1(f"{TTS_MODEL}:{TTS_VOICE}:{text}".encode()).hexdigest()
    if practice_id:
        return f"practiceSessions/{practice_id}/tts/{digest}.mp3"
    # 兜底（目前无调用方走这条；保留以防将来有不在 session 上下文里的朗读需求）
    return f"tts/{digest}.mp3"


def _synthesize(text: str) -> bytes:
    dashscope.api_key = DASHSCOPE_API_KEY
    audio = SpeechSynthesizer(model=TTS_MODEL, voice=TTS_VOICE).call(text)
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
