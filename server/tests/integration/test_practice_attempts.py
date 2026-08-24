"""独立 Attempt 链路：双读合并、并发 reserve 的 round 唯一性。"""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME

CORRECT_RESULT = {"summary": "ok", "score": 6.0, "standardAnswer": "native", "gaps": [], "progress": None}


def test_dual_read_merges_embedded_and_independent_by_round(client, user_id, auth_headers, practice_id):
    """迁移过渡期：嵌入 round 1 + 独立 round 2 合并成完整列表，且都带稳定 attemptId。"""
    mongo = MongoClient("mongodb://localhost:27017/")
    db = mongo[TEST_DB_NAME]
    db.practiceSessions.update_one(
        {"_id": practice_id},
        {"$push": {"attempts": {"round": 1, "transcript": "embedded take", "score": 5.0}}},
    )
    db.practiceAttempts.insert_one({
        "_id": "pa_independent_round2",
        "practiceId": practice_id,
        "userId": user_id,
        "round": 2,
        "transcript": "independent take",
        "score": 7.0,
        "status": "completed",
    })
    mongo.close()

    practice = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    attempts = practice["attempts"]

    assert [a["round"] for a in attempts] == [1, 2]
    assert attempts[0]["transcript"] == "embedded take"
    assert attempts[0]["attemptId"].startswith("pa_")
    assert attempts[1]["attemptId"] == "pa_independent_round2"


def test_dual_read_independent_row_wins_over_embedded_same_round(client, user_id, auth_headers, practice_id):
    mongo = MongoClient("mongodb://localhost:27017/")
    db = mongo[TEST_DB_NAME]
    db.practiceSessions.update_one(
        {"_id": practice_id},
        {"$push": {"attempts": {"round": 1, "transcript": "stale embedded"}}},
    )
    db.practiceAttempts.insert_one({
        "_id": "pa_winner",
        "practiceId": practice_id,
        "userId": user_id,
        "round": 1,
        "transcript": "fresh independent",
        "status": "completed",
    })
    mongo.close()

    practice = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()

    assert len(practice["attempts"]) == 1
    assert practice["attempts"][0]["transcript"] == "fresh independent"


def test_concurrent_corrections_get_unique_rounds(client, user_id, auth_headers, practice_id):
    """并发完成回调不产生重复 (practiceId, round)。"""
    with patch("routes.correct.correct_text", new=AsyncMock(return_value=CORRECT_RESULT)):
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(pool.map(
                lambda i: client.post(
                    "/api/correct",
                    json={
                        "userId": user_id,
                        "practiceId": practice_id,
                        "text": f"concurrent take {i}",
                    },
                    headers=auth_headers,
                ),
                range(3),
            ))

    bodies = [r.json() for r in responses]
    assert all(r.status_code == 200 for r in responses)
    assert sorted(b["round"] for b in bodies) == [1, 2, 3]
    assert len({b["attemptId"] for b in bodies}) == 3

    mongo = MongoClient("mongodb://localhost:27017/")
    docs = list(mongo[TEST_DB_NAME].practiceAttempts.find({"practiceId": practice_id}))
    mongo.close()
    pairs = [(d["practiceId"], d["round"]) for d in docs]
    assert len(pairs) == len(set(pairs)) == 3
