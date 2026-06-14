"""场景题库取题逻辑：定制题优先、未练优先。"""

from bson import ObjectId
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
    """开口评估过的题往后排：再插入一道没练过的公共题后，应优先出新题。
    注意：判定标准是 attempts 非空（开过口），只看了图没说话不算练过。
    """
    # 建练习并塞一个 attempt（模拟评估完成）
    sess = client.post("/api/practice-sessions", json={"userId": user_id, "scenarioId": scenario_id}).json()
    db = _db()
    db.practiceSessions.update_one(
        {"_id": ObjectId(sess["_id"])},
        {"$set": {"attempts": [{"transcript": "hi", "round": 1}]}},
    )
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


def test_skip_excludes_scenario(client, user_id, scenario_id):
    """exclude 参数应跳过当前题、出下一道（哪怕没开口练过也排除）。"""
    db = _db()
    db.scenarios.insert_one({
        "_id": "sc_other",
        "slug": "other",
        "where": "x", "story": "s", "mission": "m",
        "difficulty": 2, "imageKey": "scenarios/sc_other/cover.jpg",
        "ownerUserId": None,
        "status": "active",
    })
    resp = client.get(f"/api/scenarios/next?userId={user_id}&exclude={scenario_id}")
    assert resp.json()["scenarioId"] == "sc_other"


def test_only_viewed_not_excluded_next_round(client, user_id, scenario_id):
    """看了图没说话（没 attempts）不算练过：下次取题还能再出。"""
    # 建练习但不放 attempt
    client.post("/api/practice-sessions", json={"userId": user_id, "scenarioId": scenario_id})
    resp = client.get(f"/api/scenarios/next?userId={user_id}")
    assert resp.json()["scenarioId"] == scenario_id
