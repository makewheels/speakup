from unittest.mock import AsyncMock, patch


def test_transcribe_happy(client):
    fake = AsyncMock(return_value="Hello, this is a test.")
    with patch("routes.transcribe.transcribe", new=fake):
        files = {"audio": ("a.webm", b"\x00\x01\x02", "audio/webm")}
        data = {"userId": "u_test"}
        resp = client.post("/api/transcribe", files=files, data=data)
    assert resp.status_code == 200
    assert resp.json() == {"text": "Hello, this is a test."}
    fake.assert_awaited_once()


def test_transcribe_empty_audio_400(client):
    fake = AsyncMock(return_value="should not be called")
    with patch("routes.transcribe.transcribe", new=fake):
        files = {"audio": ("a.webm", b"", "audio/webm")}
        data = {"userId": "u_test"}
        resp = client.post("/api/transcribe", files=files, data=data)
    assert resp.status_code == 400
    fake.assert_not_called()
