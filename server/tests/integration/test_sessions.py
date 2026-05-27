def test_create_session_has_created_at(client, user_id):
    resp = client.post(
        "/api/sessions",
        json={"userId": user_id, "topic": "daily", "imageUrl": "https://example.com/img.jpg"},
    )
    assert resp.status_code == 200
    sess = resp.json()
    assert sess["topic"] == "daily"
    assert sess["attempts"] == []
    assert "createdAt" in sess and sess["createdAt"]


def test_list_sessions_sorted_newest_first(client, user_id):
    s1 = client.post(
        "/api/sessions",
        json={"userId": user_id, "topic": "daily", "imageUrl": "https://example.com/1"},
    ).json()
    s2 = client.post(
        "/api/sessions",
        json={"userId": user_id, "topic": "travel", "imageUrl": "https://example.com/2"},
    ).json()
    listing = client.get(f"/api/sessions/?userId={user_id}").json()
    assert [s["_id"] for s in listing] == [s2["_id"], s1["_id"]]


def test_get_session_by_id(client, session_id):
    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["_id"] == session_id


def test_get_session_missing_returns_404(client):
    resp = client.get("/api/sessions/000000000000000000000000")
    assert resp.status_code == 404


def test_upload_recording_stores_url_in_session(client, user_id, session_id, monkeypatch):
    from unittest.mock import AsyncMock
    fake_url = "https://oss.example.com/recordings/test.webm"
    monkeypatch.setattr("routes.sessions.upload_bytes_async", AsyncMock(return_value=fake_url))

    audio_bytes = b"FAKE_WEBM_DATA"
    resp = client.post(
        f"/api/sessions/{session_id}/recording",
        data={"userId": user_id},
        files={"audio": ("recording.webm", audio_bytes, "audio/webm")},
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == fake_url

    sess = client.get(f"/api/sessions/{session_id}").json()
    assert len(sess.get("recordings", [])) == 1
    assert sess["recordings"][0]["url"] == fake_url


def test_upload_recording_wrong_user_returns_404(client, user_id, session_id, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("routes.sessions.upload_bytes_async", AsyncMock(return_value="https://x"))
    other = client.post("/api/auth/login", json={"phone": "13900005678"}).json()["userId"]
    resp = client.post(
        f"/api/sessions/{session_id}/recording",
        data={"userId": other},
        files={"audio": ("r.webm", b"data", "audio/webm")},
    )
    assert resp.status_code == 404
