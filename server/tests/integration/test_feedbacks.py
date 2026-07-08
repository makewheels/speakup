from tests.conftest import login_headers


def _submit_practice(client, user_id, auth_headers, practice_id, **overrides):
    body = {
        "userId": user_id,
        "type": "practice",
        "rating": "bad",
        "tags": ["score_too_strict"],
        "comment": "我其实说得挺对的",
        "practiceId": practice_id,
        "attemptIndex": 0,
        "snapshot": {
            "score": 6.0, "summary": "x", "nativeVersion": "N",
            "gaps": [], "transcript": "t", "round": 1,
        },
    }
    body.update(overrides)
    return client.post("/api/feedbacks", json=body, headers=auth_headers)


def test_submit_practice_feedback_stores_snapshot(client, user_id, auth_headers, practice_id):
    r = _submit_practice(client, user_id, auth_headers, practice_id)
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "practice"
    assert body["rating"] == "bad"
    assert body["tags"] == ["score_too_strict"]
    assert body["practiceId"] == practice_id
    assert body["snapshot"]["score"] == 6.0
    assert body["_id"].startswith("fb_")


def test_submit_general_feedback_has_no_practice(client, user_id, auth_headers):
    r = client.post(
        "/api/feedbacks",
        json={
            "userId": user_id,
            "type": "general",
            "tags": ["bug"],
            "comment": "录音按钮点了没反应",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "general"
    assert body["rating"] is None
    assert "practiceId" not in body
    assert body["tags"] == ["bug"]


def test_practice_feedback_rejects_other_users_practice(client, user_id, auth_headers, practice_id):
    other, other_headers = login_headers(client)
    r = client.post(
        "/api/feedbacks",
        json={
            "userId": other,
            "type": "practice",
            "rating": "bad",
            "practiceId": practice_id,  # 属于 user_id，不属于 other
            "attemptIndex": 0,
        },
        headers=other_headers,
    )
    assert r.status_code == 404


def test_practice_feedback_requires_practice_id(client, user_id, auth_headers):
    r = client.post(
        "/api/feedbacks",
        json={"userId": user_id, "type": "practice", "rating": "bad"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_unknown_tags_are_dropped(client, user_id, auth_headers, practice_id):
    r = _submit_practice(
        client, user_id, auth_headers, practice_id,
        tags=["score_too_strict", "made_up_tag"],
    )
    assert r.json()["tags"] == ["score_too_strict"]


def test_list_returns_only_my_feedbacks(client, user_id, auth_headers, practice_id):
    _submit_practice(client, user_id, auth_headers, practice_id)
    other, other_headers = login_headers(client)
    client.post(
        "/api/feedbacks",
        json={"userId": other, "type": "general", "comment": "别的用户"},
        headers=other_headers,
    )
    items = client.get(f"/api/feedbacks?userId={user_id}", headers=auth_headers).json()
    assert len(items) == 1
    assert items[0]["userId"] == user_id


def test_list_rejects_userid_token_mismatch(client, user_id, auth_headers):
    other, _ = login_headers(client)
    r = client.get(f"/api/feedbacks?userId={other}", headers=auth_headers)
    assert r.status_code == 403


def test_feedback_rejects_missing_token(client):
    r = client.post("/api/feedbacks", json={"type": "general"})
    assert r.status_code == 401
