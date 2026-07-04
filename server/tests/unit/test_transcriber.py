import gzip
import json

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
