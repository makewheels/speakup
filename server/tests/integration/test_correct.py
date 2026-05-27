from unittest.mock import AsyncMock, patch

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
