"""口语发音评测的供应商适配层。

浏览器仍只拿最终 JSON；服务端用 WebSocket 调腾讯智聆录音模式，避免把密钥和供应商协议暴露出去。
"""

import asyncio
import base64
import hashlib
import hmac
import json
import random
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import websockets

from config import (
    PRONUNCIATION_APP_ID,
    PRONUNCIATION_ENABLED,
    PRONUNCIATION_ISSUE_THRESHOLD,
    PRONUNCIATION_MAX_ISSUES,
    PRONUNCIATION_PROVIDER,
    PRONUNCIATION_SCORE_COEFF,
    PRONUNCIATION_SECRET_ID,
    PRONUNCIATION_SECRET_KEY,
    PRONUNCIATION_WS_URL,
)


class PronunciationError(RuntimeError):
    pass


def pronunciation_available() -> bool:
    return bool(
        PRONUNCIATION_ENABLED
        and PRONUNCIATION_PROVIDER == "tencent"
        and PRONUNCIATION_APP_ID
        and PRONUNCIATION_SECRET_ID
        and PRONUNCIATION_SECRET_KEY
    )


def build_signed_url(
    ref_text: str,
    eval_mode: int,
    *,
    timestamp: int | None = None,
    nonce: int | None = None,
    voice_id: str | None = None,
) -> str:
    """按官方协议：未编码参数排序签名，实际请求再统一 URL encode。"""
    now = timestamp if timestamp is not None else int(time.time())
    params = {
        "eval_mode": str(eval_mode),
        "expired": str(now + 3600),
        "nonce": str(nonce if nonce is not None else random.randint(1, 2_147_483_647)),
        "rec_mode": "1",
        "ref_text": ref_text,
        "score_coeff": f"{min(4.0, max(1.0, PRONUNCIATION_SCORE_COEFF)):.1f}",
        "secretid": PRONUNCIATION_SECRET_ID,
        "sentence_info_enabled": "0",
        "server_engine_type": "16k_en",
        "text_mode": "0",
        "timestamp": str(now),
        "voice_format": "1",
        "voice_id": voice_id or str(uuid.uuid4()),
    }
    base = PRONUNCIATION_WS_URL.rstrip("/")
    signing_path = f"{base.removeprefix('wss://')}/{PRONUNCIATION_APP_ID}"
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    digest = hmac.new(
        PRONUNCIATION_SECRET_KEY.encode(), f"{signing_path}?{query}".encode(), hashlib.sha1
    ).digest()
    signature = base64.b64encode(digest).decode()
    return f"{base}/{PRONUNCIATION_APP_ID}?{urlencode({**params, 'signature': signature})}"


async def _request_evaluation(wav_bytes: bytes, ref_text: str, eval_mode: int) -> dict:
    url = build_signed_url(ref_text, eval_mode)
    try:
        async with websockets.connect(
            url,
            compression=None,
            proxy=None,
            open_timeout=15,
            close_timeout=5,
            ping_interval=None,
            max_size=4 * 1024 * 1024,
        ) as socket:
            handshake = json.loads(await socket.recv())
            if handshake.get("code") != 0:
                raise PronunciationError(f"provider handshake code {handshake.get('code')}")
            await socket.send(wav_bytes)
            await socket.send(json.dumps({"type": "end"}))
            last_result = None
            while True:
                message = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
                if message.get("code") != 0:
                    raise PronunciationError(f"provider evaluation code {message.get('code')}")
                if isinstance(message.get("result"), dict):
                    last_result = message["result"]
                if message.get("final") == 1:
                    if last_result is None:
                        raise PronunciationError("provider returned no evaluation result")
                    return last_result
    except PronunciationError:
        raise
    except Exception as error:
        # 不把带 SecretId 和签名的 WebSocket URL 包进上层日志/响应。
        raise PronunciationError(f"provider transport failed: {type(error).__name__}") from None


def _safe_suffix(suffix: str) -> str:
    value = suffix.lower().lstrip(".")
    return value if value in {"webm", "ogg", "m4a", "mp4", "wav", "mp3"} else "webm"


def _convert_to_wav(
    audio_bytes: bytes,
    suffix: str,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> bytes:
    with tempfile.TemporaryDirectory(prefix="speakup-pronunciation-") as temp_dir:
        source = Path(temp_dir) / f"input.{_safe_suffix(suffix)}"
        target = Path(temp_dir) / "output.wav"
        source.write_bytes(audio_bytes)
        command = ["ffmpeg", "-v", "error", "-y"]
        if start_ms is not None:
            command += ["-ss", f"{max(0, start_ms) / 1000:.3f}"]
        command += ["-i", str(source)]
        if end_ms is not None and start_ms is not None:
            command += ["-t", f"{max(0.1, (end_ms - start_ms) / 1000):.3f}"]
        else:
            command += ["-t", "60"]
        command += ["-ac", "1", "-ar", "16000", "-sample_fmt", "s16", "-f", "wav", str(target)]
        completed = subprocess.run(command, capture_output=True, check=False)
        if completed.returncode != 0 or not target.exists():
            raise PronunciationError("audio conversion failed")
        return target.read_bytes()


async def _wav(audio_bytes: bytes, suffix: str, start_ms=None, end_ms=None) -> bytes:
    return await asyncio.to_thread(
        _convert_to_wav, audio_bytes, suffix, start_ms=start_ms, end_ms=end_ms
    )


def _score(value, *, fraction=False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if fraction or 0 <= number <= 1:
        number *= 100
    return min(100.0, max(0.0, number))


def _candidate_words(result: dict) -> list[dict]:
    candidates = []
    for word in result.get("Words") or []:
        text = str(word.get("Word") or "").strip()
        if not re.search(r"[A-Za-z]", text) or word.get("MatchTag", 0) != 0:
            continue
        score = _score(word.get("PronAccuracy"))
        if score >= PRONUNCIATION_ISSUE_THRESHOLD:
            continue
        start = int(word.get("MemBeginTime") or 0)
        end = int(word.get("MemEndTime") or 0)
        if end <= start:
            continue
        candidates.append({"word": text, "score": score, "startMs": start, "endMs": end})
    return sorted(candidates, key=lambda item: item["score"])[:PRONUNCIATION_MAX_ISSUES]


def _coaching(phones: list[dict]) -> str:
    stress = any(phone["stressExpected"] != phone["stressDetected"] for phone in phones)
    differences = [
        (phone["detected"], phone["reference"])
        for phone in phones
        if phone["detected"] and phone["reference"] and phone["detected"] != phone["reference"]
    ]
    if differences:
        pairs = "、".join(f"/{actual}/ → /{target}/" for actual, target in differences[:2])
        suffix = "，同时留意重音位置" if stress else ""
        return f"你更接近 {pairs}；先听标准音，再慢速跟读{suffix}。"
    if stress:
        return "音素基本接近，重点调整重音位置：先夸张重读目标音节，再恢复自然语速。"
    return "这个词的清晰度还可以提高：先逐音节慢读，再连起来恢复正常语速。"


def _normalize_issue(candidate: dict, result: dict) -> dict:
    word_result = (result.get("Words") or [{}])[0]
    phones = []
    for phone in word_result.get("PhoneInfos") or []:
        phones.append({
            "detected": str(phone.get("Phone") or "").lstrip("'"),
            "reference": str(phone.get("ReferencePhone") or "").lstrip("'"),
            "score": _score(phone.get("PronAccuracy"), fraction=True),
            "stressExpected": bool(phone.get("Stress")),
            "stressDetected": bool(phone.get("DetectedStress")),
            "startMs": int(phone.get("MemBeginTime") or 0),
            "endMs": int(phone.get("MemEndTime") or 0),
        })
    return {
        **candidate,
        "score": _score(word_result.get("PronAccuracy", candidate["score"])),
        "detectedIpa": "".join(phone["detected"] for phone in phones),
        "referenceIpa": "".join(phone["reference"] for phone in phones),
        "phones": phones,
        "coaching": _coaching(phones),
    }


async def evaluate_pronunciation(audio_bytes: bytes, suffix: str, transcript: str) -> dict:
    if not pronunciation_available():
        raise PronunciationError("pronunciation provider is not configured")
    words = re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", transcript)
    if not words:
        raise PronunciationError("reference text has no English words")
    reference = " ".join(words[:120])
    mode = 1 if len(words) <= 30 else 2
    full_wav = await _wav(audio_bytes, suffix)
    first_pass = await _request_evaluation(full_wav, reference, mode)
    candidates = _candidate_words(first_pass)

    async def evaluate_word(candidate: dict) -> dict:
        start = max(0, candidate["startMs"] - 100)
        end = candidate["endMs"] + 100
        clip = await _wav(audio_bytes, suffix, start, end)
        detail = await _request_evaluation(clip, f"{{::cmd{{F_IPA=true}}}} {candidate['word']}", 4)
        return _normalize_issue(candidate, detail)

    issues = await asyncio.gather(*(evaluate_word(candidate) for candidate in candidates))
    return {
        "status": "completed",
        "provider": PRONUNCIATION_PROVIDER,
        # 腾讯建议总分展示 SuggestedScore；老响应没有时再退回准确度。
        "overallScore": _score(first_pass.get("SuggestedScore", first_pass.get("PronAccuracy"))),
        "accuracyScore": _score(first_pass.get("PronAccuracy")),
        "fluencyScore": _score(first_pass.get("PronFluency"), fraction=True),
        "completionScore": _score(first_pass.get("PronCompletion"), fraction=True),
        "issues": issues,
    }
