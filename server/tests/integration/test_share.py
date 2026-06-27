from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME, login_headers


def _add_attempt(pid, score=7.5):
    db = MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]
    db.practiceSessions.update_one(
        {"_id": pid},
        {"$set": {"attempts": [{"transcript": "hi", "round": 1, "score": score}]}},
    )


def test_share_creates_token_and_public_read(client, user_id, auth_headers, practice_id):
    resp = client.post(
        f"/api/practice-sessions/{practice_id}/share",
        json={"userId": user_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    token = resp.json()["shareToken"]
    assert token
    assert token.isalnum()  # 纯字母数字，无 - / _ 等特殊字符

    pub = client.get(f"/api/share/{token}")
    assert pub.status_code == 200
    body = pub.json()
    assert body["_id"] == practice_id
    assert "ownerNickname" in body and body["ownerNickname"]  # 昵称已解析


def test_share_is_idempotent(client, user_id, auth_headers, practice_id):
    t1 = client.post(
        f"/api/practice-sessions/{practice_id}/share",
        json={"userId": user_id},
        headers=auth_headers,
    ).json()["shareToken"]
    t2 = client.post(
        f"/api/practice-sessions/{practice_id}/share",
        json={"userId": user_id},
        headers=auth_headers,
    ).json()["shareToken"]
    assert t1 == t2  # 复用同一 token


def test_unshare_keeps_token_and_reshare_reuses_link(client, user_id, auth_headers, practice_id):
    token = client.post(
        f"/api/practice-sessions/{practice_id}/share",
        json={"userId": user_id},
        headers=auth_headers,
    ).json()["shareToken"]
    assert client.get(f"/api/share/{token}").status_code == 200

    # 取消分享：旧链接立即 404（shared=False），但 token 保留
    client.request(
        "DELETE",
        f"/api/practice-sessions/{practice_id}/share?userId={user_id}",
        headers=auth_headers,
    )
    assert client.get(f"/api/share/{token}").status_code == 404

    # 再次开启：复用同一 token，旧链接复活
    token2 = client.post(
        f"/api/practice-sessions/{practice_id}/share",
        json={"userId": user_id},
        headers=auth_headers,
    ).json()["shareToken"]
    assert token2 == token
    assert client.get(f"/api/share/{token}").status_code == 200


def test_share_wrong_user_404(client, user_id, practice_id):
    other, other_headers = login_headers(client, "13900008888")
    resp = client.post(
        f"/api/practice-sessions/{practice_id}/share",
        json={"userId": other},
        headers=other_headers,
    )
    assert resp.status_code == 404


def test_get_shared_invalid_token_404(client):
    assert client.get("/api/share/nonexistent_token").status_code == 404


def test_shared_only_filter(client, user_id, auth_headers, scenario_id):
    p1 = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
        headers=auth_headers,
    ).json()
    p2 = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
        headers=auth_headers,
    ).json()
    _add_attempt(p1["_id"])
    _add_attempt(p2["_id"])
    client.post(
        f"/api/practice-sessions/{p1['_id']}/share",
        json={"userId": user_id},
        headers=auth_headers,
    )

    shared = client.get(
        f"/api/practice-sessions/?userId={user_id}&sharedOnly=true",
        headers=auth_headers,
    ).json()
    ids = [p["_id"] for p in shared]
    assert p1["_id"] in ids
    assert p2["_id"] not in ids


def test_share_rejects_missing_token(client, user_id, practice_id):
    resp = client.post(f"/api/practice-sessions/{practice_id}/share", json={"userId": user_id})
    assert resp.status_code == 401
