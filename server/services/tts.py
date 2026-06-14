"""文本转语音：DashScope CosyVoice 合成英文朗读，结果按文本哈希缓存到 OSS。

点击朗读时才合成；同一句话第二次直接走 OSS 缓存，不再花钱。
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


def _cache_key(text: str) -> str:
    digest = hashlib.sha1(f"{TTS_MODEL}:{TTS_VOICE}:{text}".encode()).hexdigest()
    return f"tts/{digest}.mp3"


def _synthesize(text: str) -> bytes:
    dashscope.api_key = DASHSCOPE_API_KEY
    audio = SpeechSynthesizer(model=TTS_MODEL, voice=TTS_VOICE).call(text)
    if not audio:
        raise RuntimeError("TTS 无音频返回")
    return audio


async def speak_url(text: str) -> str:
    """返回这句话朗读音频的 OSS 签名 URL。命中缓存直接返回，否则合成后存 OSS。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")
    key = _cache_key(text)
    if not await asyncio.to_thread(exists, key):
        audio = await asyncio.to_thread(_synthesize, text)
        await asyncio.to_thread(upload_bytes, key, audio, "audio/mpeg")
    return await asyncio.to_thread(get_url, key)
