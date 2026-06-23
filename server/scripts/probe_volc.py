"""探测火山 Agent Plan API：文字 / 图片 / TTS / ASR / 视频任务列表。

跑：cd server && uv run python scripts/probe_volc.py
读 .env 的 CHAT_API_KEY；不会打印 key。
"""

import asyncio
import gzip
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import websockets
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ARK_KEY = os.getenv("ARK_API_KEY") or os.getenv("CHAT_API_KEY")
if not ARK_KEY:
    sys.exit("缺 ARK_API_KEY（或 CHAT_API_KEY 兜底）")

ARK_PLAN_BASE = "https://ark.cn-beijing.volces.com/api/plan/v3"
SPEECH_BASE = "https://openspeech.bytedance.com/api/v3/plan"
ASR_URL = "wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_nostream"


def _short(value, n=500):
    text = str(value).replace(ARK_KEY, "<redacted>")
    return text if len(text) <= n else text[:n] + f"...(+{len(text) - n})"


async def probe_chat():
    print("\n=== [1/5] 文字模型 ===")
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(
            f"{ARK_PLAN_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {ARK_KEY}", "Content-Type": "application/json"},
            json={
                "model": "ark-code-latest",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
        )
    print("status:", r.status_code)
    print(_short(r.text, 300))


async def probe_image():
    print("\n=== [2/5] 图片生成 ===")
    async with httpx.AsyncClient(timeout=180.0) as c:
        r = await c.post(
            f"{ARK_PLAN_BASE}/images/generations",
            headers={"Authorization": f"Bearer {ARK_KEY}", "Content-Type": "application/json"},
            json={
                "model": "doubao-seedream-5.0-lite",
                "prompt": "a red apple on a wooden table, photograph",
                "size": "2560x1440",
                "n": 1,
                "response_format": "url",
            },
        )
    print("status:", r.status_code)
    print(_short(r.text, 500))


async def probe_tts():
    print("\n=== [3/5] TTS ===")
    headers = {
        "Authorization": f"Bearer {ARK_KEY}",
        "X-Api-Key": ARK_KEY,
        "X-Api-App-Key": "plan",
        "X-Api-Access-Key": ARK_KEY,
        "X-Api-Resource-Id": "seed-tts-2.0",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    payload = {
        "user": {"uid": "probe"},
        "req_params": {
            "text": "Hello world.",
            "speaker": "zh_female_vv_uranus_bigtts",
            "audio_params": {"format": "mp3", "sample_rate": 24000},
        },
    }
    async with httpx.AsyncClient(timeout=90.0) as c:
        r = await c.post(f"{SPEECH_BASE}/tts/unidirectional", headers=headers, json=payload)
    print("status:", r.status_code, "bytes:", len(r.content), "content-type:", r.headers.get("content-type"))
    print(_short(r.text, 300))


def _header(message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    return bytes([(1 << 4) | 1, (message_type << 4) | flags, (serialization << 4) | compression, 0])


def _frame(message_type: int, flags: int, serialization: int, payload: bytes) -> bytes:
    compressed = gzip.compress(payload)
    return _header(message_type, flags, serialization, 1) + len(compressed).to_bytes(4, "big") + compressed


def _parse_asr(message: bytes | str) -> tuple[dict, bool]:
    if isinstance(message, str):
        return {"text": message}, False
    header_size = (message[0] & 0x0F) * 4
    message_type = (message[1] & 0xF0) >> 4
    flags = message[1] & 0x0F
    compression = message[2] & 0x0F
    offset = header_size
    if message_type == 0xF:
        code = int.from_bytes(message[offset:offset + 4], "big")
        offset += 4
        size = int.from_bytes(message[offset:offset + 4], "big")
        offset += 4
        return {"error_code": code, "error": message[offset:offset + size].decode("utf-8", "replace")}, True
    if flags in (1, 3):
        offset += 4
    size = int.from_bytes(message[offset:offset + 4], "big")
    offset += 4
    payload = message[offset:offset + size]
    if compression == 1:
        payload = gzip.decompress(payload)
    return json.loads(payload.decode()), flags == 3


async def probe_asr():
    print("\n=== [4/5] ASR WebSocket ===")
    start = {
        "user": {"uid": "probe"},
        "audio": {"format": "mp3", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1, "language": "en-US"},
        "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True, "enable_lid": False, "result_type": "full"},
    }
    silent = bytes.fromhex("fffb9064000003480100000348010000034801000003480100000348010000034801") * 80
    headers = {
        "Authorization": f"Bearer {ARK_KEY}",
        "X-Api-Key": ARK_KEY,
        "X-Api-App-Key": "plan",
        "X-Api-Access-Key": ARK_KEY,
        "X-Api-Resource-Id": "volc.seedasr.sauc.duration",
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
    async with websockets.connect(
        ASR_URL,
        additional_headers=headers,
        compression=None,
        proxy=None,
        open_timeout=15,
        ping_interval=None,
    ) as ws:
        await ws.send(_frame(1, 0, 1, json.dumps(start).encode()))
        data, final = _parse_asr(await asyncio.wait_for(ws.recv(), timeout=15))
        print("start:", _short(json.dumps(data, ensure_ascii=False), 300), "final=", final)
        await ws.send(_frame(2, 2, 0, silent))
        data, final = _parse_asr(await asyncio.wait_for(ws.recv(), timeout=20))
        print("audio:", _short(json.dumps(data, ensure_ascii=False), 300), "final=", final)


async def probe_video_list():
    print("\n=== [5/5] 视频任务列表 ===")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(
            f"{ARK_PLAN_BASE}/contents/generations/tasks",
            headers={"Authorization": f"Bearer {ARK_KEY}"},
            params={"page_num": 1, "page_size": 1},
        )
    print("status:", r.status_code)
    print(_short(r.text, 500))


async def main():
    await probe_chat()
    await probe_image()
    await probe_tts()
    await probe_asr()
    await probe_video_list()


if __name__ == "__main__":
    asyncio.run(main())
