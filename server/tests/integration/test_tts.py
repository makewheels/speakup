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


def test_tts_passes_practice_id_to_speak_url(client):
    """前端传 practiceId → 路由原样透传给 speak_url，让音频挂到 session 下。"""
    fake = AsyncMock(return_value="https://oss.example/practiceSessions/sess_x/tts/abc.mp3?sig=x")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post(
            "/api/tts",
            json={"text": "Could you remake my latte?", "practiceId": "sess_x"},
        )
    assert resp.status_code == 200
    fake.assert_awaited_once()
    assert fake.await_args.kwargs.get("practice_id") == "sess_x"


def test_tts_without_practice_id_still_works(client):
    """不传 practiceId 也能调通（兜底走全局 tts/）。"""
    fake = AsyncMock(return_value="https://oss.example/tts/abc.mp3?sig=x")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "Hi"})
    assert resp.status_code == 200
    assert fake.await_args.kwargs.get("practice_id") is None
