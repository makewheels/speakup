from tests.conftest import login_headers


def test_create_practice_snapshots_scenario(client, user_id, auth_headers, scenario_id):
    resp = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    p = resp.json()
    assert p["_id"].startswith("ps_")
    assert p["scenarioId"] == scenario_id
    assert p["topic"] == "☕️ 测试咖啡店"
    assert p["scenario"]["mission"]
    assert p["imageKey"] == "scenarios/sc_test_coffee/cover.jpg"
    assert p["imageUrl"]  # imageKey 现签出 URL
    assert p["videoKey"] == "scenarios/sc_test_coffee/cover.mp4"
    assert p["videoUrl"]  # videoKey 现签出 URL
    assert p["attempts"] == []
    assert "createdAt" in p and p["createdAt"]


def test_create_practice_unknown_scenario_404(client, user_id, auth_headers):
    resp = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": "sc_nope"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def _add_attempt(db, pid):
    db.practiceSessions.update_one(
        {"_id": pid},
        {"$set": {"attempts": [{"transcript": "hi", "round": 1}]}},
    )


def test_list_practices_sorted_newest_first(client, user_id, auth_headers, scenario_id):
    from pymongo import MongoClient
    from tests.conftest import TEST_DB_NAME
    db = MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]
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
    _add_attempt(db, p1["_id"])
    _add_attempt(db, p2["_id"])
    listing = client.get(f"/api/practice-sessions/?userId={user_id}", headers=auth_headers).json()
    assert [p["_id"] for p in listing] == [p2["_id"], p1["_id"]]


def test_list_practices_excludes_empty(client, user_id, auth_headers, scenario_id):
    """没开口（attempts 为空）的 session 不进历史列表。"""
    from pymongo import MongoClient
    from tests.conftest import TEST_DB_NAME
    db = MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]
    empty = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
        headers=auth_headers,
    ).json()
    spoken = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
        headers=auth_headers,
    ).json()
    _add_attempt(db, spoken["_id"])
    listing = client.get(f"/api/practice-sessions/?userId={user_id}", headers=auth_headers).json()
    ids = [p["_id"] for p in listing]
    assert spoken["_id"] in ids
    assert empty["_id"] not in ids


def test_get_practice_by_id(client, auth_headers, practice_id):
    resp = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["_id"] == practice_id


def test_get_practice_missing_returns_404(client, auth_headers):
    resp = client.get("/api/practice-sessions/000000000000000000000000", headers=auth_headers)
    assert resp.status_code == 404


def test_get_legacy_objectid_practice_by_id(client, user_id, auth_headers, scenario_id):
    from bson import ObjectId
    from pymongo import MongoClient
    from tests.conftest import TEST_DB_NAME

    oid = ObjectId()
    db = MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]
    db.practiceSessions.insert_one({
        "_id": oid,
        "userId": user_id,
        "scenarioId": scenario_id,
        "title": "legacy",
        "topic": "legacy topic",
        "scenario": {},
        "imageKey": "",
        "videoKey": "",
        "attempts": [],
    })

    resp = client.get(f"/api/practice-sessions/{oid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["_id"] == str(oid)


def test_upload_recording_stores_key_and_returns_signed_url(
    client,
    user_id,
    auth_headers,
    practice_id,
    monkeypatch,
):
    from unittest.mock import AsyncMock, MagicMock
    fake_signed = "https://oss.example.com/rec.webm?Signature=abc"
    monkeypatch.setattr("routes.practice_sessions.upload_bytes_async", AsyncMock(return_value=None))
    monkeypatch.setattr("routes.practice_sessions.oss_signed_url", MagicMock(return_value=fake_signed))

    audio_bytes = b"FAKE_WEBM_DATA"
    resp = client.post(
        f"/api/practice-sessions/{practice_id}/recording",
        data={"userId": user_id},
        files={"audio": ("recording.webm", audio_bytes, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == fake_signed

    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert len(p.get("recordings", [])) == 1
    rec = p["recordings"][0]
    assert "key" in rec                          # key 存入 DB
    assert rec.get("url") == fake_signed         # 读取时返回签名 URL
    # 路径规范：practiceSessions/{userId}/{yyyyMM}/{practiceId}/recording/{ts}.{ext}
    parts = rec["key"].split("/")
    assert parts[0] == "practiceSessions" and parts[1] == user_id and parts[3] == practice_id
    assert parts[4] == "recording"
    assert len(parts[2]) == 6  # yyyyMM


def test_upload_recording_links_attempt(client, user_id, auth_headers, practice_id, monkeypatch):
    """attemptIndex 合法时，录音 key 要写进对应 attempt。"""
    from unittest.mock import AsyncMock, MagicMock, patch
    monkeypatch.setattr("routes.practice_sessions.upload_bytes_async", AsyncMock(return_value=None))
    monkeypatch.setattr("routes.practice_sessions.oss_signed_url", MagicMock(return_value="https://signed"))

    fake_result = {"summary": "s", "nativeVersion": "n", "gaps": [], "progress": None}
    with patch("routes.correct.correct_text", new=AsyncMock(return_value=fake_result)):
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "one two three four"},
            headers=auth_headers,
        )

    resp = client.post(
        f"/api/practice-sessions/{practice_id}/recording",
        data={"userId": user_id, "attemptIndex": 0},
        files={"audio": ("r.webm", b"data", "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert p["attempts"][0].get("recordingKey")
    assert p["attempts"][0].get("recordingUrl") == "https://signed"


def test_upload_recording_wrong_user_returns_404(client, user_id, practice_id, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("routes.practice_sessions.upload_bytes_async", AsyncMock(return_value=None))
    other, other_headers = login_headers(client, "13900005678")
    resp = client.post(
        f"/api/practice-sessions/{practice_id}/recording",
        data={"userId": other},
        files={"audio": ("r.webm", b"data", "audio/webm")},
        headers=other_headers,
    )
    assert resp.status_code == 404


def test_get_practice_rejects_missing_token(client, practice_id):
    resp = client.get(f"/api/practice-sessions/{practice_id}")
    assert resp.status_code == 401


def test_get_practice_rejects_other_user(client, practice_id):
    _, other_headers = login_headers(client, "13900006666")
    resp = client.get(f"/api/practice-sessions/{practice_id}", headers=other_headers)
    assert resp.status_code == 404


def test_create_practice_rejects_userid_token_mismatch(client, user_id, auth_headers, scenario_id):
    other, _ = login_headers(client, "13900007777")
    resp = client.post(
        "/api/practice-sessions",
        json={"userId": other, "scenarioId": scenario_id},
        headers=auth_headers,
    )
    assert resp.status_code == 403
