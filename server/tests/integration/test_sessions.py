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
