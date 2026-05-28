import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

FAKE_AI_RESULT = {
    "summary": "Two grammar slips, otherwise the meaning lands.",
    "nativeVersion": "A few people are cooking in a sunlit kitchen.",
    "gaps": [
        {
            "original": "some peoples",
            "better": "some people",
            "why": "'people' is already plural.",
            "category": "grammar",
            "saveToReview": True,
        },
        {
            "original": "she is make coffee",
            "better": "she is making coffee",
            "why": "be + V-ing for present continuous.",
            "category": "grammar",
            "saveToReview": False,
        },
    ],
}


def _mock_correct():
    return patch("routes.correct.correct_text", new=AsyncMock(return_value=FAKE_AI_RESULT))


def test_correct_returns_layered_schema(client, user_id, session_id):
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "sessionId": session_id,
                "text": "There is some peoples in the kitchen.",
                "imageUrl": "https://example.com/img.jpg",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]
    assert data["nativeVersion"]
    assert len(data["gaps"]) == 2
    g = data["gaps"][0]
    assert set(g.keys()) >= {"original", "better", "why", "category", "saveToReview"}


def test_correct_persists_attempt_into_session(client, user_id, session_id):
    with _mock_correct():
        client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "sessionId": session_id,
                "text": "test text here ok",
                "imageUrl": "https://example.com/img.jpg",
            },
        )
    sess = client.get(f"/api/sessions/{session_id}").json()
    assert len(sess["attempts"]) == 1
    a = sess["attempts"][0]
    assert a["transcript"] == "test text here ok"
    assert a["summary"] == FAKE_AI_RESULT["summary"]
    assert a["gaps"] == FAKE_AI_RESULT["gaps"]
    assert "createdAt" in a


def test_correct_autosaves_flagged_gaps_to_vocabulary(client, user_id, session_id):
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "sessionId": session_id,
                "text": "There is some peoples in the kitchen.",
                "imageUrl": "https://example.com/img.jpg",
            },
        )
    assert resp.json()["autoSaved"] == 1  # only gap[0] has saveToReview=True

    vocab = client.get(f"/api/vocabulary/?userId={user_id}").json()
    assert len(vocab) == 1
    assert vocab[0]["word"] == "some people"


def test_correct_no_duplicate_vocab_on_retry(client, user_id, session_id):
    with _mock_correct():
        for _ in range(2):
            client.post(
                "/api/correct",
                json={
                    "userId": user_id,
                    "sessionId": session_id,
                    "text": "There is some peoples.",
                    "imageUrl": "",
                },
            )
    vocab = client.get(f"/api/vocabulary/?userId={user_id}").json()
    words = [v["word"] for v in vocab]
    assert words.count("some people") == 1


def test_correct_rejects_other_users_session(client, user_id, session_id):
    other = client.post("/api/auth/login", json={"phone": "13900001234"}).json()["userId"]
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": other, "sessionId": session_id, "text": "x y z", "imageUrl": ""},
        )
    assert resp.status_code == 404


# ── _get_image_url 单元测试 ──────────────────────────────────────────────────

def test_get_image_url_uses_signed_url_when_file_archived(client, user_id):
    """fileId 存在时应生成 OSS 签名 URL，而不是用 ossImageUrl（bucket private 会 403）。"""
    from routes.correct import _get_image_url

    fake_file_doc = {
        "_id": "f_abc123",
        "variants": {"orig": {"key": "files/f_abc123/orig.jpg", "url": "https://oss.example.com/files/f_abc123/orig.jpg"}},
    }
    fake_signed = "https://oss.example.com/files/f_abc123/orig.jpg?Signature=xxx&Expires=999"

    session = {
        "fileId": "f_abc123",
        "imageUrl": "https://loremflickr.com/640/640/cat",
        "ossImageUrl": "https://oss.example.com/files/f_abc123/orig.jpg",
    }

    with patch("routes.correct.get_db") as mock_db, \
         patch("routes.correct.oss_signed_url", return_value=fake_signed):
        mock_db.return_value.files.find_one = AsyncMock(return_value=fake_file_doc)
        result = asyncio.run(_get_image_url(session, "https://req.example.com/img.jpg"))

    assert result == fake_signed


def test_get_image_url_falls_back_to_loremflickr_when_no_file(client, user_id):
    """fileId 不存在时用 session.imageUrl（loremflickr），不用 ossImageUrl。"""
    from routes.correct import _get_image_url

    session = {
        "imageUrl": "https://loremflickr.com/640/640/cat",
        "ossImageUrl": "https://oss.example.com/private.jpg",
    }
    result = asyncio.run(_get_image_url(session, "https://req.example.com/img.jpg"))
    assert result == "https://loremflickr.com/640/640/cat"


def test_get_image_url_falls_back_to_req_when_session_has_no_imageurl(client, user_id):
    """session 没有 imageUrl 时用请求里的 imageUrl。"""
    from routes.correct import _get_image_url

    result = asyncio.run(_get_image_url({}, "https://req.example.com/img.jpg"))
    assert result == "https://req.example.com/img.jpg"
