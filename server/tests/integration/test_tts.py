from unittest.mock import AsyncMock, patch


def test_tts_happy(client):
    fake = AsyncMock(return_value="https://oss.example/tts/abc.mp3?sig=x")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "Could I get a refund?"})
    assert resp.status_code == 200
    assert resp.json() == {"url": "https://oss.example/tts/abc.mp3?sig=x"}
    fake.assert_awaited_once()


def test_tts_empty_text_400(client):
    fake = AsyncMock(return_value="should not be called")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "   "})
    assert resp.status_code == 400
    fake.assert_not_called()


def test_tts_too_long_413(client):
    fake = AsyncMock(return_value="nope")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "x" * 601})
    assert resp.status_code == 413
    fake.assert_not_called()
