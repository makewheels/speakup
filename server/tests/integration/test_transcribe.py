from unittest.mock import AsyncMock, patch


def test_transcribe_happy(client, user_id, auth_headers):
    fake = AsyncMock(return_value="Hello, this is a test.")
    with patch("routes.transcribe.transcribe", new=fake):
        files = {"audio": ("a.webm", b"\x00\x01\x02", "audio/webm")}
        data = {"userId": user_id}
        resp = client.post("/api/transcribe", files=files, data=data, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"text": "Hello, this is a test."}
    fake.assert_awaited_once()


def test_transcribe_empty_audio_400(client, user_id, auth_headers):
    fake = AsyncMock(return_value="should not be called")
    with patch("routes.transcribe.transcribe", new=fake):
        files = {"audio": ("a.webm", b"", "audio/webm")}
        data = {"userId": user_id}
        resp = client.post("/api/transcribe", files=files, data=data, headers=auth_headers)
    assert resp.status_code == 400
    fake.assert_not_called()


def test_transcribe_rejects_missing_token(client, user_id):
    files = {"audio": ("a.webm", b"\x00\x01\x02", "audio/webm")}
    resp = client.post("/api/transcribe", files=files, data={"userId": user_id})
    assert resp.status_code == 401
