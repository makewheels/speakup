import gzip
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from services import transcriber
from services.transcriber import _AUDIO_CHUNK_BYTES, _audio_chunks, _full_client_request


def test_audio_chunks_splits_large_payload_and_keeps_tail():
    data = b"a" * (_AUDIO_CHUNK_BYTES + 7)

    chunks = _audio_chunks(data)

    assert len(chunks) == 2
    assert len(chunks[0]) == _AUDIO_CHUNK_BYTES
    assert chunks[1] == b"a" * 7


def test_full_client_request_declares_pcm_raw_audio():
    frame = _full_client_request()
    size = int.from_bytes(frame[4:8], "big", signed=False)
    payload = gzip.decompress(frame[8:8 + size])
    data = json.loads(payload.decode())

    assert data["audio"]["format"] == "pcm"
    assert data["audio"]["codec"] == "raw"
    assert data["audio"]["rate"] == 16000
    assert data["audio"]["channel"] == 1


@pytest.mark.asyncio
async def test_dashscope_asr_posts_wav_data_url_and_reads_transcript(monkeypatch):
    captured = {}
    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "hello from speakup."}}]},
        request=httpx.Request("POST", "https://example.test/chat/completions"),
    )

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, payload=json)
            return response

    monkeypatch.setattr(transcriber, "_to_wav", AsyncMock(return_value=b"RIFFfake-wav"))
    monkeypatch.setattr(transcriber.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(transcriber, "VOICE_ASR_URL", "https://example.test/chat/completions")

    text = await transcriber._transcribe_dashscope(b"browser-audio", ".webm")

    assert text == "Hello from speakup."
    audio = captured["payload"]["messages"][0]["content"][0]["input_audio"]["data"]
    assert audio.startswith("data:audio/wav;base64,")
    assert captured["payload"]["asr_options"]["language"] == "en"
