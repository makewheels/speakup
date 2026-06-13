def test_create_practice_snapshots_scenario(client, user_id, scenario_id):
    resp = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
    )
    assert resp.status_code == 200
    p = resp.json()
    assert p["scenarioId"] == scenario_id
    assert p["topic"] == "☕️ 测试咖啡店"
    assert p["scenario"]["mission"]
    assert p["imageKey"] == "scenarios/sc_test_coffee/cover.jpg"
    assert p["imageUrl"]  # imageKey 现签出 URL
    assert p["attempts"] == []
    assert "createdAt" in p and p["createdAt"]


def test_create_practice_unknown_scenario_404(client, user_id):
    resp = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": "sc_nope"},
    )
    assert resp.status_code == 404


def test_list_practices_sorted_newest_first(client, user_id, scenario_id):
    p1 = client.post(
        "/api/practice-sessions", json={"userId": user_id, "scenarioId": scenario_id}
    ).json()
    p2 = client.post(
        "/api/practice-sessions", json={"userId": user_id, "scenarioId": scenario_id}
    ).json()
    listing = client.get(f"/api/practice-sessions/?userId={user_id}").json()
    assert [p["_id"] for p in listing] == [p2["_id"], p1["_id"]]


def test_get_practice_by_id(client, practice_id):
    resp = client.get(f"/api/practice-sessions/{practice_id}")
    assert resp.status_code == 200
    assert resp.json()["_id"] == practice_id


def test_get_practice_missing_returns_404(client):
    resp = client.get("/api/practice-sessions/000000000000000000000000")
    assert resp.status_code == 404


def test_upload_recording_stores_key_and_returns_signed_url(client, user_id, practice_id, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    fake_signed = "https://oss.example.com/rec.webm?Signature=abc"
    monkeypatch.setattr("routes.practice_sessions.upload_bytes_async", AsyncMock(return_value=None))
    monkeypatch.setattr("routes.practice_sessions.oss_signed_url", MagicMock(return_value=fake_signed))

    audio_bytes = b"FAKE_WEBM_DATA"
    resp = client.post(
        f"/api/practice-sessions/{practice_id}/recording",
        data={"userId": user_id},
        files={"audio": ("recording.webm", audio_bytes, "audio/webm")},
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == fake_signed

    p = client.get(f"/api/practice-sessions/{practice_id}").json()
    assert len(p.get("recordings", [])) == 1
    rec = p["recordings"][0]
    assert "key" in rec                          # key 存入 DB
    assert rec.get("url") == fake_signed         # 读取时返回签名 URL
    # 路径规范：practiceSessions/{userId}/{yyyyMM}/{practiceId}/recording/{ts}.{ext}
    parts = rec["key"].split("/")
    assert parts[0] == "practiceSessions" and parts[1] == user_id and parts[3] == practice_id
    assert parts[4] == "recording"
    assert len(parts[2]) == 6  # yyyyMM


def test_upload_recording_links_attempt(client, user_id, practice_id, monkeypatch):
    """attemptIndex 合法时，录音 key 要写进对应 attempt。"""
    from unittest.mock import AsyncMock, MagicMock, patch
    monkeypatch.setattr("routes.practice_sessions.upload_bytes_async", AsyncMock(return_value=None))
    monkeypatch.setattr("routes.practice_sessions.oss_signed_url", MagicMock(return_value="https://signed"))

    fake_result = {"summary": "s", "nativeVersion": "n", "gaps": [], "progress": None}
    with patch("routes.correct.correct_text", new=AsyncMock(return_value=fake_result)):
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "one two three four"},
        )

    resp = client.post(
        f"/api/practice-sessions/{practice_id}/recording",
        data={"userId": user_id, "attemptIndex": 0},
        files={"audio": ("r.webm", b"data", "audio/webm")},
    )
    assert resp.status_code == 200
    p = client.get(f"/api/practice-sessions/{practice_id}").json()
    assert p["attempts"][0].get("recordingKey")
    assert p["attempts"][0].get("recordingUrl") == "https://signed"


def test_upload_recording_wrong_user_returns_404(client, user_id, practice_id, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("routes.practice_sessions.upload_bytes_async", AsyncMock(return_value=None))
    other = client.post("/api/auth/login", json={"phone": "13900005678"}).json()["userId"]
    resp = client.post(
        f"/api/practice-sessions/{practice_id}/recording",
        data={"userId": other},
        files={"audio": ("r.webm", b"data", "audio/webm")},
    )
    assert resp.status_code == 404
