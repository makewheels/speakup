"""渐进式场景提示：slug 精确取题、创建会话幂等/重校验、提示原子领取、Attempt 计数。"""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME, login_headers

PROGRESSIVE_SCENARIO = {
    "_id": "sc_prog_coffee",
    "slug": "prog-coffee-remake",
    "kind": "task",
    "interactionType": "progressive_hints",
    "title": "咖啡店重做饮品",
    "where": "咖啡店 · 西雅图",
    "story": "店员把你的热拿铁做成了冰拿铁，你赶时间想尽快解决。",
    "mission": "礼貌说明问题，请店员重做。",
    "points": ["说明饮品做错了", "要求重做一杯热的"],
    "hints": ["我点的是热拿铁，但这杯是冰的。", "能麻烦你重新做一杯热的吗？"],
    "difficulty": 2,
    "imageKey": "",
    "videoKey": "",
    "ownerUserId": None,
    "status": "active",
}


def _db():
    return MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]


def _seed(doc):
    db = _db()
    db.scenarios.insert_one(deepcopy(doc))


def _create_session(client, auth_headers, user_id, scenario_id, request_id=None):
    body = {"userId": user_id, "scenarioId": scenario_id}
    if request_id is not None:
        body["requestId"] = request_id
    return client.post("/api/practice-sessions", json=body, headers=auth_headers)


# ---------- GET /api/scenarios/by-slug/{slug} ----------

def test_by_slug_returns_progressive_scenario(client, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    resp = client.get("/api/scenarios/by-slug/prog-coffee-remake", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenarioId"] == "sc_prog_coffee"
    assert data["interactionType"] == "progressive_hints"
    assert data["hints"] == PROGRESSIVE_SCENARIO["hints"]
    assert data["difficulty"] == 2
    assert data["points"] == PROGRESSIVE_SCENARIO["points"]
    assert data["mission"] == PROGRESSIVE_SCENARIO["mission"]


def test_by_slug_normalizes_legacy_scenario(client, auth_headers, scenario_id):
    """旧题缺 interactionType：归一为 standard + hints 空数组。"""
    resp = client.get("/api/scenarios/by-slug/test-coffee", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["interactionType"] == "standard"
    assert data["hints"] == []


def test_by_slug_missing_archived_invalid_all_404(client, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    assert client.get("/api/scenarios/by-slug/no-such-slug", headers=auth_headers).status_code == 404
    assert client.get("/api/scenarios/by-slug/UPPER-CASE", headers=auth_headers).status_code == 404
    _db().scenarios.update_one({"_id": "sc_prog_coffee"}, {"$set": {"status": "archived"}})
    assert client.get("/api/scenarios/by-slug/prog-coffee-remake", headers=auth_headers).status_code == 404


def test_by_slug_cannot_read_other_users_custom(client, auth_headers):
    custom = {
        **PROGRESSIVE_SCENARIO,
        "_id": "sc_prog_custom",
        "slug": "prog-custom-other",
        "ownerUserId": "u_someone_else",
    }
    _seed(custom)
    resp = client.get("/api/scenarios/by-slug/prog-custom-other", headers=auth_headers)
    assert resp.status_code == 404


# ---------- POST /api/practice-sessions（重校验 + 幂等） ----------

def test_create_session_snapshots_progressive_fields(client, user_id, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    resp = _create_session(client, auth_headers, user_id, "sc_prog_coffee", "req-start-1")
    assert resp.status_code == 200
    p = resp.json()
    assert p["scenario"]["interactionType"] == "progressive_hints"
    assert p["scenario"]["hints"] == PROGRESSIVE_SCENARIO["hints"]
    assert p["scenario"]["difficulty"] == 2
    assert p["revealedHintCount"] == 0
    assert p["creationRequestId"] == "req-start-1"


def test_create_session_revalidates_archived_scenario(client, user_id, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    _db().scenarios.update_one({"_id": "sc_prog_coffee"}, {"$set": {"status": "archived"}})
    resp = _create_session(client, auth_headers, user_id, "sc_prog_coffee")
    assert resp.status_code == 404
    assert _db().practiceSessions.count_documents({"userId": user_id}) == 0


def test_create_session_rejects_other_users_scenario(client, user_id, auth_headers):
    custom = {**PROGRESSIVE_SCENARIO, "_id": "sc_prog_custom2", "ownerUserId": "u_someone_else"}
    _seed(custom)
    assert _create_session(client, auth_headers, user_id, "sc_prog_custom2").status_code == 404


def test_create_session_same_request_id_is_idempotent(client, user_id, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    first = _create_session(client, auth_headers, user_id, "sc_prog_coffee", "req-dup")
    second = _create_session(client, auth_headers, user_id, "sc_prog_coffee", "req-dup")
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["_id"] == second.json()["_id"]
    assert _db().practiceSessions.count_documents({"userId": user_id}) == 1


def test_create_session_same_request_id_conflicting_params_409(client, user_id, auth_headers, scenario_id):
    _seed(PROGRESSIVE_SCENARIO)
    first = _create_session(client, auth_headers, user_id, "sc_prog_coffee", "req-conflict")
    assert first.status_code == 200
    other = _create_session(client, auth_headers, user_id, scenario_id, "req-conflict")
    assert other.status_code == 409


def test_create_session_request_id_scoped_per_user(client, user_id, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    _create_session(client, auth_headers, user_id, "sc_prog_coffee", "req-shared")
    other_uid, other_headers = login_headers(client, "13900009999")
    resp = _create_session(client, other_headers, other_uid, "sc_prog_coffee", "req-shared")
    assert resp.status_code == 200
    assert resp.json()["userId"] == other_uid


def test_create_session_without_request_id_keeps_legacy_shape(client, user_id, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    resp = _create_session(client, auth_headers, user_id, "sc_prog_coffee")
    assert resp.status_code == 200
    assert "creationRequestId" not in resp.json()


# ---------- POST /api/practice-sessions/{pid}/hints/next ----------

def _progressive_session(client, user_id, auth_headers):
    _seed(PROGRESSIVE_SCENARIO)
    resp = _create_session(client, auth_headers, user_id, "sc_prog_coffee")
    return resp.json()["_id"]


def _reveal(client, auth_headers, pid, request_id):
    return client.post(
        f"/api/practice-sessions/{pid}/hints/next",
        json={"requestId": request_id},
        headers=auth_headers,
    )


def test_reveal_walks_hints_in_order_then_exhausts(client, user_id, auth_headers):
    pid = _progressive_session(client, user_id, auth_headers)
    first = _reveal(client, auth_headers, pid, "req-h1")
    assert first.status_code == 200
    assert first.json() == {
        "requestId": "req-h1",
        "revealedHintCount": 1,
        "hintIndex": 0,
        "hint": PROGRESSIVE_SCENARIO["hints"][0],
        "exhausted": False,
    }
    second = _reveal(client, auth_headers, pid, "req-h2")
    assert second.json()["revealedHintCount"] == 2
    assert second.json()["hint"] == PROGRESSIVE_SCENARIO["hints"][1]
    assert second.json()["exhausted"] is True
    third = _reveal(client, auth_headers, pid, "req-h3")
    assert third.status_code == 200
    assert third.json() == {
        "requestId": "req-h3",
        "revealedHintCount": 2,
        "hintIndex": None,
        "hint": None,
        "exhausted": True,
    }
    assert _db().practiceSessions.find_one({"_id": pid})["revealedHintCount"] == 2


def test_reveal_same_request_id_replays_without_increment(client, user_id, auth_headers):
    pid = _progressive_session(client, user_id, auth_headers)
    first = _reveal(client, auth_headers, pid, "req-retry")
    retry = _reveal(client, auth_headers, pid, "req-retry")
    assert first.json() == retry.json()
    session = _db().practiceSessions.find_one({"_id": pid})
    assert session["revealedHintCount"] == 1
    assert len(session["hintReveals"]) == 1


def test_reveal_state_restores_on_session_read(client, user_id, auth_headers):
    """刷新恢复：GET 会话返回服务端计数与快照提示，前端据此渲染前缀。"""
    pid = _progressive_session(client, user_id, auth_headers)
    _reveal(client, auth_headers, pid, "req-a")
    session = client.get(f"/api/practice-sessions/{pid}", headers=auth_headers).json()
    assert session["revealedHintCount"] == 1
    assert session["scenario"]["hints"] == PROGRESSIVE_SCENARIO["hints"]
    assert session["scenario"]["interactionType"] == "progressive_hints"


def test_reveal_on_standard_session_is_409(client, user_id, auth_headers, practice_id):
    resp = _reveal(client, auth_headers, practice_id, "req-x")
    assert resp.status_code == 409


def test_reveal_on_missing_or_foreign_session_is_404(client, user_id, auth_headers):
    pid = _progressive_session(client, user_id, auth_headers)
    assert _reveal(client, auth_headers, "ps_no_such", "req-x").status_code == 404
    _, other_headers = login_headers(client, "13900008888")
    assert _reveal(client, other_headers, pid, "req-x").status_code == 404


def test_reveal_rejects_empty_request_id(client, user_id, auth_headers):
    pid = _progressive_session(client, user_id, auth_headers)
    assert _reveal(client, auth_headers, pid, "").status_code == 422
    assert client.post(
        f"/api/practice-sessions/{pid}/hints/next", json={}, headers=auth_headers
    ).status_code == 422


# ---------- Attempt hintCount ----------

FAKE_AI_RESULT = {
    "summary": "请求语气可以更礼貌。",
    "standardAnswer": "Excuse me, my latte was iced but I ordered it hot.",
    "standardAnswerNotes": [],
    "gaps": [],
    "progress": None,
}


def test_attempt_copies_hint_count_and_ignores_client_value(client, user_id, auth_headers):
    pid = _progressive_session(client, user_id, auth_headers)
    _reveal(client, auth_headers, pid, "req-h1")
    with patch("routes.correct.correct_text", new=AsyncMock(return_value=deepcopy(FAKE_AI_RESULT))):
        resp = client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "practiceId": pid,
                "text": "My latte is iced but I ordered it hot.",
                "hintCount": 99,
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    attempt = _db().practiceAttempts.find_one({"practiceId": pid})
    assert attempt["hintCount"] == 1


def test_standard_attempt_hint_count_defaults_zero(client, user_id, auth_headers, practice_id):
    with patch("routes.correct.correct_text", new=AsyncMock(return_value=deepcopy(FAKE_AI_RESULT))):
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Could you remake it, please?"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    attempt = _db().practiceAttempts.find_one({"practiceId": practice_id})
    assert attempt["hintCount"] == 0
