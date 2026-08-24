import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from pymongo import MongoClient
from tests.conftest import TEST_DB_NAME, login_headers


def _ensure_attempt(practice_id, attempt_index):
    db = MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]
    practice = db.practiceSessions.find_one({"_id": practice_id})
    attempt_id = f"pa_test_{practice_id}_{attempt_index + 1}"
    db.practiceAttempts.update_one(
        {"_id": attempt_id},
        {"$setOnInsert": {
            "practiceId": practice_id,
            "userId": practice["userId"],
            "sourceType": practice.get("sourceType", "human"),
            "round": attempt_index + 1,
            "status": "completed",
            "transcript": "test",
            "createdAt": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    db.practiceSessions.update_one({"_id": practice_id}, {"$max": {"attemptSeq": attempt_index + 1}})
    return attempt_id


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
    index = body.get("attemptIndex", 0)
    body["attemptId"] = body.get("attemptId") or _ensure_attempt(practice_id, index)
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
    assert body["sourceType"] == "human"
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
    assert body["sourceType"] == "human"
    assert "practiceId" not in body
    assert body["tags"] == ["bug"]


def test_ai_test_feedback_inherits_source(client, scenario_id):
    login = client.post(
        "/api/auth/login",
        json={"phone": "13900009995", "sourceType": "ai_test"},
    ).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    practice = client.post(
        "/api/practice-sessions",
        json={"userId": login["userId"], "scenarioId": scenario_id},
        headers=headers,
    ).json()

    practice_feedback = _submit_practice(
        client, login["userId"], headers, practice["_id"]
    ).json()
    general_feedback = client.post(
        "/api/feedbacks",
        json={"type": "general", "tags": ["bug"], "comment": "自动体验"},
        headers=headers,
    ).json()

    assert practice_feedback["sourceType"] == "ai_test"
    assert general_feedback["sourceType"] == "ai_test"


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


def test_practice_feedback_upserts_same_attempt(client, user_id, auth_headers, practice_id):
    # 同一 attempt 再提交 = 更新同一条，不新增
    r1 = _submit_practice(client, user_id, auth_headers, practice_id, comment="第一次")
    r2 = _submit_practice(client, user_id, auth_headers, practice_id, comment="改成这样", rating="good")
    assert r1.json()["_id"] == r2.json()["_id"]
    assert r2.json()["comment"] == "改成这样"
    assert r2.json()["rating"] == "good"
    items = client.get(f"/api/feedbacks?userId={user_id}", headers=auth_headers).json()
    assert len(items) == 1


def test_practice_feedback_separate_attempts_are_separate(client, user_id, auth_headers, practice_id):
    _submit_practice(client, user_id, auth_headers, practice_id, attemptIndex=0)
    _submit_practice(client, user_id, auth_headers, practice_id, attemptIndex=1)
    items = client.get(f"/api/feedbacks?userId={user_id}", headers=auth_headers).json()
    assert len(items) == 2


def test_list_filters_by_practice_and_attempt(client, user_id, auth_headers, practice_id):
    _submit_practice(client, user_id, auth_headers, practice_id, attemptIndex=0)
    _submit_practice(client, user_id, auth_headers, practice_id, attemptIndex=1)
    items = client.get(
        f"/api/feedbacks?userId={user_id}&practiceId={practice_id}&attemptIndex=0",
        headers=auth_headers,
    ).json()
    assert len(items) == 1
    assert items[0]["attemptIndex"] == 0


def test_submit_clears_historical_duplicates(client, user_id, auth_headers, practice_id):
    # 模拟早期 insert_one 在同一 attempt 留下的多条历史反馈
    db = MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]
    db.feedbacks.insert_many([
        {"_id": "fb_old1", "userId": user_id, "type": "practice", "rating": "bad",
         "practiceId": practice_id, "attemptIndex": 0, "tags": [], "comment": "旧1"},
        {"_id": "fb_old2", "userId": user_id, "type": "practice", "rating": "bad",
         "practiceId": practice_id, "attemptIndex": 0, "tags": [], "comment": "旧2"},
    ])
    # 再提交一次：upsert 更新一条 + 清理多余，最终只剩一条
    _submit_practice(client, user_id, auth_headers, practice_id, comment="新的")
    items = client.get(f"/api/feedbacks?userId={user_id}", headers=auth_headers).json()
    assert len(items) == 1
    assert items[0]["comment"] == "新的"


def test_general_feedback_uploads_multiple_original_images_without_reencoding(
    client, user_id, auth_headers, monkeypatch,
):
    uploaded = AsyncMock()
    monkeypatch.setattr("routes.feedbacks.upload_bytes_async", uploaded)
    png = b"\x89PNG\r\n\x1a\nORIGINAL-PNG-BYTES"
    jpeg = b"\xff\xd8\xffORIGINAL-JPEG-BYTES"

    response = client.post(
        "/api/feedbacks/with-images",
        data={"payload": json.dumps({
            "type": "general", "tags": ["bug"], "comment": "移动端按钮错位",
        })},
        files=[
            ("images", ("screen-one.png", png, "image/png")),
            ("images", ("screen-two.jpg", jpeg, "image/jpeg")),
        ],
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "general"
    assert len(body["images"]) == 2
    assert body["images"][0]["fileName"] == "screen-one.png"
    assert body["images"][0]["key"].startswith(f"feedbacks/{user_id}/")
    assert uploaded.await_args_list[0].args[1:] == (png, "image/png")
    assert uploaded.await_args_list[1].args[1:] == (jpeg, "image/jpeg")

    stored = MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME].feedbacks.find_one(
        {"_id": body["_id"]}
    )
    assert "url" not in stored["images"][0]
    assert stored["images"][0]["sizeBytes"] == len(png)


def test_practice_feedback_images_keep_attempt_association(
    client, user_id, auth_headers, practice_id, monkeypatch,
):
    monkeypatch.setattr("routes.feedbacks.upload_bytes_async", AsyncMock())
    attempt_id = _ensure_attempt(practice_id, 1)
    response = client.post(
        "/api/feedbacks/with-images",
        data={"payload": json.dumps({
            "type": "practice",
            "rating": "bad",
            "practiceId": practice_id,
            "attemptId": attempt_id,
            "attemptIndex": 1,
            "comment": "第二轮布局有问题",
        })},
        files=[("images", ("layout.png", b"\x89PNG\r\n\x1a\nraw", "image/png"))],
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["practiceId"] == practice_id
    assert response.json()["attemptIndex"] == 1
    assert response.json()["attemptId"] == attempt_id
    assert len(response.json()["images"]) == 1


def test_invalid_later_image_cleans_already_uploaded_objects(
    client, auth_headers, monkeypatch,
):
    uploaded = AsyncMock()
    deleted = AsyncMock()
    monkeypatch.setattr("routes.feedbacks.upload_bytes_async", uploaded)
    monkeypatch.setattr("routes.feedbacks.delete_async", deleted)
    response = client.post(
        "/api/feedbacks/with-images",
        data={"payload": json.dumps({"type": "general", "comment": "有问题"})},
        files=[
            ("images", ("valid.png", b"\x89PNG\r\n\x1a\nraw", "image/png")),
            ("images", ("fake.svg", b"<svg></svg>", "image/svg+xml")),
        ],
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert uploaded.await_count == 1
    assert deleted.await_count == 1
