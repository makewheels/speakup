from services.transcriber import _AUDIO_CHUNK_BYTES, _audio_chunks


def test_audio_chunks_splits_large_payload_and_keeps_tail():
    data = b"a" * (_AUDIO_CHUNK_BYTES + 7)

    chunks = _audio_chunks(data)

    assert len(chunks) == 2
    assert len(chunks[0]) == _AUDIO_CHUNK_BYTES
    assert chunks[1] == b"a" * 7
