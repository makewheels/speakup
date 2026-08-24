from unittest.mock import AsyncMock, patch

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME


def test_tts_happy(client, auth_headers):
    fake = AsyncMock(return_value="https://oss.example/tts/abc.mp3?sig=x")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post(
            "/api/tts",
            json={"text": "Could I get a refund?"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json() == {"url": "https://oss.example/tts/abc.mp3?sig=x"}
    fake.assert_awaited_once()


def test_tts_empty_text_400(client, auth_headers):
    fake = AsyncMock(return_value="should not be called")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "   "}, headers=auth_headers)
    assert resp.status_code == 400
    fake.assert_not_called()


def test_tts_too_long_413(client, auth_headers):
    fake = AsyncMock(return_value="nope")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "x" * 601}, headers=auth_headers)
    assert resp.status_code == 413
    fake.assert_not_called()


def test_tts_passes_practice_id_to_speak_url(client, auth_headers, practice_id):
    """带业务上下文的朗读按用户、月份、session、attempt 和用途归档。"""
    mongo = MongoClient("mongodb://localhost:27017/")
    practice = mongo[TEST_DB_NAME].practiceSessions.find_one({"_id": practice_id})
    attempt_id = "pa_1787579000000aaaaaaaaaa"
    mongo[TEST_DB_NAME].practiceAttempts.insert_one({
        "_id": attempt_id,
        "practiceId": practice_id,
        "userId": practice["userId"],
        "round": 1,
        "status": "completed",
        "createdAt": practice["createdAt"],
    })
    mongo.close()
    fake = AsyncMock(return_value="https://oss.example/speech.wav?sig=x")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post(
            "/api/tts",
            json={
                "text": "Could you remake my latte?",
                "practiceId": practice_id,
                "attemptId": attempt_id,
                "purpose": "correction",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    fake.assert_awaited_once()
    key = fake.await_args.kwargs["storage_key"]
    assert f"/{practice_id}/attempts/{attempt_id}/speech/correction/sp_" in key
    practice = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert practice["attempts"][0]["speechAssets"][0]["key"] == key


def test_tts_without_practice_id_still_works(client, auth_headers):
    """不传 practiceId 也能调通（兜底走全局 speech/global/）。"""
    fake = AsyncMock(return_value="https://oss.example/tts/abc.mp3?sig=x")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "Hi"}, headers=auth_headers)
    assert resp.status_code == 200
    assert fake.await_args.kwargs.get("storage_key") is None


def test_tts_rejects_missing_token(client):
    fake = AsyncMock(return_value="should not be called")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post("/api/tts", json={"text": "Hi"})
    assert resp.status_code == 401
    fake.assert_not_called()


def test_tts_unknown_practice_404(client, auth_headers):
    resp = client.post(
        "/api/tts",
        json={"text": "Hi", "practiceId": "ps_does_not_exist"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_tts_without_any_attempt_409(client, auth_headers, practice_id):
    resp = client.post(
        "/api/tts",
        json={"text": "Hi", "practiceId": practice_id},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_tts_archives_into_legacy_embedded_attempt(client, auth_headers, practice_id):
    """独立 Attempt 不存在时，speechAssets 回退写嵌入数组。"""
    mongo = MongoClient("mongodb://localhost:27017/")
    mongo[TEST_DB_NAME].practiceSessions.update_one(
        {"_id": practice_id}, {"$push": {"attempts": {"round": 1}}}
    )
    mongo.close()
    fake = AsyncMock(return_value="https://oss.example/speech.wav?sig=x")
    with patch("routes.tts.speak_url", new=fake):
        resp = client.post(
            "/api/tts",
            json={
                "text": "Could you remake my latte?",
                "practiceId": practice_id,
                "purpose": "standard-answer",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    mongo = MongoClient("mongodb://localhost:27017/")
    practice = mongo[TEST_DB_NAME].practiceSessions.find_one({"_id": practice_id})
    mongo.close()
    assets = practice["attempts"][0]["speechAssets"]
    assert len(assets) == 1
    assert assets[0]["purpose"] == "standard-answer"
    assert "/attempts/pa_" in assets[0]["key"]
