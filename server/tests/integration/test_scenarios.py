"""场景题库取题逻辑：定制题优先、未练优先。"""

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME


def _db():
    return MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]


def test_next_returns_public_scenario(client, user_id, scenario_id):
    resp = client.get(f"/api/scenarios/next?userId={user_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenarioId"] == scenario_id
    assert data["mission"]
    assert data["isCustom"] is False
    assert data["imageUrl"]  # imageKey 现签出 URL


def test_next_empty_library_404(client, user_id):
    resp = client.get(f"/api/scenarios/next?userId={user_id}")
    assert resp.status_code == 404


def test_custom_scenario_preferred(client, user_id, scenario_id):
    db = _db()
    db.scenarios.insert_one({
        "_id": "sc_custom1",
        "slug": "custom-1",
        "where": "🏨 定制酒店",
        "story": "s",
        "mission": "m",
        "difficulty": 2,
        "imageKey": "scenarios/sc_custom1/cover.jpg",
        "ownerUserId": user_id,
        "targetWords": ["I'm in a rush"],
        "status": "active",
    })
    resp = client.get(f"/api/scenarios/next?userId={user_id}")
    data = resp.json()
    assert data["scenarioId"] == "sc_custom1"
    assert data["isCustom"] is True
    assert data["targetWords"] == ["I'm in a rush"]


def test_other_users_custom_not_served(client, user_id, scenario_id):
    db = _db()
    db.scenarios.insert_one({
        "_id": "sc_custom_other",
        "slug": "custom-other",
        "where": "x", "story": "s", "mission": "m",
        "difficulty": 2, "imageKey": "scenarios/sc_custom_other/cover.jpg",
        "ownerUserId": "u_someoneelse",
        "status": "active",
    })
    resp = client.get(f"/api/scenarios/next?userId={user_id}")
    assert resp.json()["scenarioId"] == scenario_id


def test_practiced_scenario_deprioritized(client, user_id, scenario_id):
    """练过的题往后排：再插入一道没练过的公共题后，应优先出新题。"""
    # 练第一题（建练习即视为已开练）
    client.post("/api/practice-sessions", json={"userId": user_id, "scenarioId": scenario_id})
    db = _db()
    db.scenarios.insert_one({
        "_id": "sc_fresh",
        "slug": "fresh",
        "where": "🏨 新题", "story": "s", "mission": "m",
        "difficulty": 3, "imageKey": "scenarios/sc_fresh/cover.jpg",
        "ownerUserId": None,
        "status": "active",
    })
    resp = client.get(f"/api/scenarios/next?userId={user_id}")
    assert resp.json()["scenarioId"] == "sc_fresh"
