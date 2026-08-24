import time
from datetime import datetime, timezone

from pymongo import MongoClient

from scripts.migrate_attempt_entities import Stats, cleanup_sessions, migrate_session
from scripts.storage_orphan_cleanup import audit_orphans
from services.oss_storage import ObjectInfo
from tests.conftest import TEST_DB_NAME


def test_attempt_migration_moves_database_links_and_cleans_verified_legacy_objects(
    client,
    practice_id,
    user_id,
    monkeypatch,
):
    mongo = MongoClient("mongodb://localhost:27017/")
    db = mongo[TEST_DB_NAME]
    created = datetime(2026, 8, 24, tzinfo=timezone.utc)
    source = f"practiceSessions/{practice_id}/recording/1787579000000.webm"
    smoke = "tts/18df045b681aea316da4f866c0ca2b6da94c33b3.wav"
    db.practiceSessions.update_one(
        {"_id": practice_id},
        {"$set": {
            "createdAt": created,
            "attempts": [{
                "round": 1,
                "transcript": "Could you remake this?",
                "summary": "ok",
                "score": 6.5,
                "gaps": [],
                "recordingKey": source,
                "createdAt": created,
            }],
        }},
    )
    db.feedbacks.insert_one({
        "_id": "fb_legacy",
        "userId": user_id,
        "practiceId": practice_id,
        "attemptIndex": 0,
        "type": "practice",
    })
    db.reviewItems.insert_one({
        "_id": "rv_legacy",
        "userId": user_id,
        "practiceId": practice_id,
        "attemptIndex": 0,
    })
    db.llmCalls.insert_one({
        "_id": "llm_legacy",
        "linkedTo": {"sessionId": practice_id, "attemptIndex": 0},
    })

    objects = {source: b"recording", smoke: b"smoke"}

    def exists(key):
        return key in objects

    def info(key):
        data = objects[key]
        return ObjectInfo(key, len(data), f"etag-{len(data)}", None, int(time.time()) - 7200)

    def copy_verified(source_key, target_key):
        objects[target_key] = objects[source_key]
        return info(target_key)

    def iter_objects(prefix):
        return [info(key) for key in sorted(objects) if key.startswith(prefix)]

    monkeypatch.setattr("services.oss_storage.exists", exists)
    monkeypatch.setattr("services.oss_storage.object_info", info)
    monkeypatch.setattr("services.oss_storage.copy_verified", copy_verified)
    monkeypatch.setattr("services.oss_storage.iter_objects", iter_objects)
    monkeypatch.setattr("services.oss_storage.delete", lambda key: objects.pop(key))

    practice = db.practiceSessions.find_one({"_id": practice_id})
    stats = Stats()
    migrate_session(practice, db, execute=True, stats=stats)

    attempt = db.practiceAttempts.find_one({"practiceId": practice_id, "round": 1})
    assert attempt["_id"].startswith("pa_")
    assert f"/attempts/{attempt['_id']}/recordings/" in attempt["recording"]["key"]
    assert db.feedbacks.find_one({"_id": "fb_legacy"})["attemptId"] == attempt["_id"]
    assert db.reviewItems.find_one({"_id": "rv_legacy"})["attemptId"] == attempt["_id"]
    assert db.llmCalls.find_one({"_id": "llm_legacy"})["linkedTo"]["attemptId"] == attempt["_id"]

    cleanup_sessions(db, stats)
    audit_orphans(db, cleanup=True, stats=stats)

    session = db.practiceSessions.find_one({"_id": practice_id})
    assert "attempts" not in session
    assert attempt["recording"]["key"] in objects
    assert source not in objects
    assert smoke not in objects
    assert stats.deleted == 2
    assert len([
        key for key in objects if key not in {attempt["recording"]["key"]}
    ]) == 0
    mongo.close()
