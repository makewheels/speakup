"""自由说话题路由 + 抽题/补题闭环（真 Mongo，LLM 全 mock）。"""

import json
from unittest.mock import AsyncMock, MagicMock

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME, login_headers


def _db():
    """返回 (client, database)——用完要 close 的是 client，不是 database。"""
    mc = MongoClient("mongodb://localhost:27017/")
    return mc, mc[TEST_DB_NAME]


def _seed_topics(*topics):
    mc, db = _db()
    db.freeTopics.insert_many([
        {"_id": f"ft_{i}", "slug": t["slug"], "text": t["text"], "zh": t.get("zh", ""),
         "status": t.get("status", "active"), "sourceType": "seed"}
        for i, t in enumerate(topics, 1)
    ])
    mc.close()


def _fake_llm_client(payload: str):
    resp = MagicMock()
    resp.content = payload
    resp.response_metadata = {
        "model_name": "test-model",
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    client = MagicMock()
    client.ainvoke = AsyncMock(return_value=resp)
    return client


def test_next_free_topic_returns_active_topic(client, user_id, auth_headers):
    _seed_topics(
        {"slug": "your-favorite-breakfast", "text": "Your favorite breakfast", "zh": "你最喜欢的早餐"},
        {"slug": "your-hometown", "text": "Your hometown", "zh": "你的家乡"},
    )
    resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["_id"].startswith("ft_")
    assert data["text"] in {"Your favorite breakfast", "Your hometown"}
    assert data["zh"]


def test_next_free_topic_skips_archived(client, user_id, auth_headers):
    _seed_topics(
        {"slug": "archived-one", "text": "Archived topic", "status": "archived"},
        {"slug": "active-one", "text": "Active topic"},
    )
    for _ in range(3):
        resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
        assert resp.json()["text"] == "Active topic"


def test_next_free_topic_excludes_practiced_topics(client, user_id, auth_headers):
    """说过（有 attempt）的话题不再抽。"""
    _seed_topics(
        {"slug": "practiced-one", "text": "Practiced topic"},
        {"slug": "fresh-one", "text": "Fresh topic"},
    )
    mc, db = _db()
    db.practiceSessions.insert_one({
        "_id": "ps_free_done",
        "userId": user_id,
        "mode": "free",
        "freeTopicId": "ft_1",          # = practiced-one
        "freeTopic": "Practiced topic",
        "attempts": [{"round": 1, "transcript": "I said something"}],
    })
    mc.close()
    for _ in range(3):
        resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
        assert resp.json()["_id"] == "ft_2"


def test_session_without_attempt_does_not_exclude_topic(client, user_id, auth_headers):
    """建了会话但没开口（无 attempt）不算说过，话题仍可抽到。"""
    _seed_topics({"slug": "only-one", "text": "Only topic"})
    mc, db = _db()
    db.practiceSessions.insert_one({
        "_id": "ps_free_empty", "userId": user_id, "mode": "free",
        "freeTopicId": "ft_1", "freeTopic": "Only topic", "attempts": [],
    })
    mc.close()
    resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
    assert resp.json()["_id"] == "ft_1"


def test_other_users_attempts_do_not_exclude(client, user_id, auth_headers):
    _seed_topics({"slug": "only-one", "text": "Only topic"})
    mc, db = _db()
    db.practiceSessions.insert_one({
        "_id": "ps_free_other", "userId": "u_someone_else", "mode": "free",
        "freeTopicId": "ft_1", "freeTopic": "Only topic",
        "attempts": [{"round": 1, "transcript": "x y z"}],
    })
    mc.close()
    resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
    assert resp.json()["_id"] == "ft_1"


def test_empty_pool_triggers_llm_topup_then_returns_topic(client, user_id, auth_headers, monkeypatch):
    """池子用完 → 自动调 LLM 补一批再抽（LLM 用假客户端 mock）。"""
    payload = json.dumps([
        {"text": "Your dream vacation", "zh": "梦想中的假期"},
        {"text": "A memorable trip", "zh": "一次难忘的旅行"},
    ])
    monkeypatch.setattr("services.corrector._get_client", lambda: _fake_llm_client(payload))

    resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["text"] in {"Your dream vacation", "A memorable trip"}

    mc, db = _db()
    count = db.freeTopics.count_documents({"status": "active"})
    mc.close()
    assert count == 2   # 补题落库且幂等键为 slug


def test_topup_is_slug_idempotent(client, user_id, auth_headers, monkeypatch):
    """库里唯一话题已说过 → 触发补题；补出的重复 slug 不再插一遍。"""
    _seed_topics({"slug": "your-dream-vacation", "text": "Your dream vacation"})
    mc, db = _db()
    db.practiceSessions.insert_one({
        "_id": "ps_free_done2", "userId": user_id, "mode": "free",
        "freeTopicId": "ft_1", "freeTopic": "Your dream vacation",
        "attempts": [{"round": 1, "transcript": "I said something"}],
    })
    mc.close()
    payload = json.dumps([
        {"text": "Your dream vacation", "zh": "重复话题"},
        {"text": "A memorable trip", "zh": "一次难忘的旅行"},
    ])
    monkeypatch.setattr("services.corrector._get_client", lambda: _fake_llm_client(payload))

    resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["text"] == "A memorable trip"
    mc, db = _db()
    assert db.freeTopics.count_documents({}) == 2   # 重复 slug 没重复插
    assert db.freeTopics.count_documents({"slug": "your-dream-vacation"}) == 1
    mc.close()


def test_empty_pool_and_llm_failure_returns_404(client, user_id, auth_headers, monkeypatch):
    """无话题且补题失败 → 404，前端可退到无话题自由说。"""
    failing = MagicMock()
    failing.ainvoke = AsyncMock(side_effect=RuntimeError("no llm in tests"))
    monkeypatch.setattr("services.corrector._get_client", lambda: failing)

    resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_next_requires_auth(client, user_id):
    assert client.get(f"/api/free-topics/next?userId={user_id}").status_code == 401


def test_next_rejects_other_users_id(client, user_id, auth_headers):
    _, other_headers = login_headers(client, "13900008888")
    resp = client.get(f"/api/free-topics/next?userId={user_id}", headers=other_headers)
    assert resp.status_code == 403
