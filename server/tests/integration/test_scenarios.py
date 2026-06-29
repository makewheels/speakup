"""场景题库取题逻辑：定制题优先、未练优先。"""

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME


def _db():
    return MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]


def test_next_returns_public_scenario(client, user_id, auth_headers, scenario_id):
    resp = client.get(f"/api/scenarios/next?userId={user_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["scenarioId"] == scenario_id
    assert data["mission"]
    assert data["isCustom"] is False
    assert data["imageUrl"]  # imageKey 现签出 URL
    assert data["videoUrl"]  # videoKey 现签出 URL


def test_next_empty_library_404(client, user_id, auth_headers):
    resp = client.get(f"/api/scenarios/next?userId={user_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_custom_scenario_preferred(client, user_id, auth_headers, scenario_id):
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
    resp = client.get(f"/api/scenarios/next?userId={user_id}", headers=auth_headers)
    data = resp.json()
    assert data["scenarioId"] == "sc_custom1"
    assert data["isCustom"] is True
    assert data["targetWords"] == ["I'm in a rush"]


def test_custom_scenario_not_preferred_for_regular_goal(client, user_id, auth_headers, scenario_id):
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
    resp = client.get(
        f"/api/scenarios/next?userId={user_id}&level=daily&purpose=openup",
        headers=auth_headers,
    )
    data = resp.json()
    assert data["scenarioId"] == scenario_id
    assert data["isCustom"] is False


def test_custom_scenario_preferred_for_review_goal(client, user_id, auth_headers, scenario_id):
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
    resp = client.get(
        f"/api/scenarios/next?userId={user_id}&level=daily&purpose=review",
        headers=auth_headers,
    )
    data = resp.json()
    assert data["scenarioId"] == "sc_custom1"
    assert data["isCustom"] is True


def test_other_users_custom_not_served(client, user_id, auth_headers, scenario_id):
    db = _db()
    db.scenarios.insert_one({
        "_id": "sc_custom_other",
        "slug": "custom-other",
        "where": "x", "story": "s", "mission": "m",
        "difficulty": 2, "imageKey": "scenarios/sc_custom_other/cover.jpg",
        "ownerUserId": "u_someoneelse",
        "status": "active",
    })
    resp = client.get(f"/api/scenarios/next?userId={user_id}", headers=auth_headers)
    assert resp.json()["scenarioId"] == scenario_id


def test_next_filters_by_level_and_purpose(client, user_id, auth_headers, scenario_id):
    db = _db()
    db.scenarios.insert_many([
        {
            "_id": "sc_travel_hard",
            "slug": "travel-hard",
            "kind": "task",
            "where": "机场海关",
            "story": "s",
            "mission": "m",
            "difficulty": 3,
            "category": {"domain": "travel", "subId": "travel.customs"},
            "imageKey": "scenarios/sc_travel_hard/cover.jpg",
            "ownerUserId": None,
            "status": "active",
        },
        {
            "_id": "sc_work_easy",
            "slug": "work-easy",
            "kind": "chat",
            "where": "茶水间",
            "story": "s",
            "mission": "m",
            "difficulty": 1,
            "category": {"domain": "work", "subId": "work.tea_room_chat"},
            "imageKey": "scenarios/sc_work_easy/cover.jpg",
            "ownerUserId": None,
            "status": "active",
        },
    ])
    resp = client.get(
        f"/api/scenarios/next?userId={user_id}&level=challenge&purpose=travel",
        headers=auth_headers,
    )
    data = resp.json()
    assert data["scenarioId"] == "sc_travel_hard"
    assert data["preferenceMatch"] == "exact"


def test_next_reports_fallback_when_preference_pool_is_sparse(
    client,
    user_id,
    auth_headers,
    scenario_id,
):
    resp = client.get(
        f"/api/scenarios/next?userId={user_id}&level=challenge&purpose=work",
        headers=auth_headers,
    )
    data = resp.json()
    assert data["scenarioId"] == scenario_id
    assert data["preferenceMatch"] == "fallback"


def test_practiced_scenario_deprioritized(client, user_id, auth_headers, scenario_id):
    """开口评估过的题往后排：再插入一道没练过的公共题后，应优先出新题。
    注意：判定标准是 attempts 非空（开过口），只看了图没说话不算练过。
    """
    # 建练习并塞一个 attempt（模拟评估完成）
    sess = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
        headers=auth_headers,
    ).json()
    db = _db()
    db.practiceSessions.update_one(
        {"_id": sess["_id"]},
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
    resp = client.get(f"/api/scenarios/next?userId={user_id}", headers=auth_headers)
    assert resp.json()["scenarioId"] == "sc_fresh"


def test_skip_excludes_scenario(client, user_id, auth_headers, scenario_id):
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
    resp = client.get(
        f"/api/scenarios/next?userId={user_id}&exclude={scenario_id}",
        headers=auth_headers,
    )
    assert resp.json()["scenarioId"] == "sc_other"


def test_only_viewed_not_excluded_next_round(client, user_id, auth_headers, scenario_id):
    """看了图没说话（没 attempts）不算练过：下次取题还能再出。"""
    # 建练习但不放 attempt
    client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
        headers=auth_headers,
    )
    resp = client.get(f"/api/scenarios/next?userId={user_id}", headers=auth_headers)
    assert resp.json()["scenarioId"] == scenario_id


def test_repeated_switch_no_immediate_repeat(client, user_id, auth_headers, scenario_id):
    """连续换题（累加 exclude）应一直给没出现过的题，直到题库穷尽——不重复给当前题。"""
    db = _db()
    for i in range(4):
        db.scenarios.insert_one({
            "_id": f"sc_p{i}",
            "slug": f"p{i}",
            "where": "x", "story": "s", "mission": "m",
            "difficulty": 2, "imageKey": f"scenarios/sc_p{i}/cover.jpg",
            "ownerUserId": None,
            "status": "active",
        })
    # 共 5 道公共题（含 fixture 的 coffee）。连换 5 次，累加 exclude，应全不同。
    seen, excludes = [], []
    for _ in range(5):
        q = "".join(f"&exclude={e}" for e in excludes)
        sid = client.get(
            f"/api/scenarios/next?userId={user_id}{q}",
            headers=auth_headers,
        ).json()["scenarioId"]
        seen.append(sid)
        excludes.append(sid)
    assert len(set(seen)) == 5  # 5 道全不重复


def test_next_rejects_missing_token(client, user_id, scenario_id):
    resp = client.get(f"/api/scenarios/next?userId={user_id}")
    assert resp.status_code == 401
