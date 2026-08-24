"""Single access layer for independent practiceAttempts with a legacy embedded fallback."""

import hashlib
import re
from datetime import datetime, timezone

from pymongo import ReturnDocument

from db.connection import get_db
from utils.data_source import normalize_source_type
from utils.id_generator import practice_attempt_id
from utils.mongo_ids import id_filter


def _public_attempt(attempt: dict) -> dict:
    item = dict(attempt)
    item["_id"] = str(item["_id"])
    item["attemptId"] = item["_id"]
    return item


def legacy_attempt_id(practice: dict, attempt: dict, round_no: int) -> str:
    """Stable ID used by the migration and by the one-release legacy reader."""
    created_at = attempt.get("createdAt") or practice.get("createdAt")
    if isinstance(created_at, datetime):
        millis = int(created_at.timestamp() * 1000)
    else:
        match = re.search(r"(\d{13})", str(created_at or practice.get("_id") or ""))
        millis = int(match.group(1)) if match else 0
    digest = hashlib.sha1(f"{practice.get('_id')}:{round_no}".encode()).hexdigest()[:10]
    return f"pa_{millis:013d}{digest}"


async def list_attempts(practice: dict, *, include_incomplete: bool = False) -> list[dict]:
    query: dict = {"practiceId": str(practice["_id"])}
    if not include_incomplete:
        query["status"] = "completed"
    docs = await get_db().practiceAttempts.find(query).sort("round", 1).to_list(None)
    by_round = {int(item.get("round") or 0): _public_attempt(item) for item in docs}

    # Transitional read only. Merge by round so a session remains readable if a
    # deploy creates a new independent Attempt before the production migration
    # has moved every older embedded Attempt.
    for index, raw in enumerate(practice.get("attempts", [])):
        item = dict(raw)
        attempt_id = item.get("attemptId") or item.get("_id")
        round_no = int(item.get("round") or index + 1)
        if round_no in by_round:
            continue
        item["round"] = round_no
        stable_id = str(attempt_id or legacy_attempt_id(practice, item, round_no))
        item["_id"] = stable_id
        item["attemptId"] = stable_id
        by_round[round_no] = item
    return [by_round[key] for key in sorted(by_round)]


async def hydrate_practice(practice: dict, *, include_incomplete: bool = False) -> dict:
    result = dict(practice)
    result["_id"] = str(result["_id"])
    result["attempts"] = await list_attempts(practice, include_incomplete=include_incomplete)
    return result


async def resolve_attempt(
    practice: dict,
    *,
    attempt_id: str = "",
    attempt_index: int = -1,
    include_incomplete: bool = False,
) -> dict | None:
    if attempt_id:
        found = await get_db().practiceAttempts.find_one({
            **id_filter(attempt_id),
            "practiceId": str(practice["_id"]),
        })
        if found and (include_incomplete or found.get("status") == "completed"):
            return _public_attempt(found)
    attempts = await list_attempts(practice, include_incomplete=include_incomplete)
    if not attempts:
        return None
    index = attempt_index if 0 <= attempt_index < len(attempts) else len(attempts) - 1
    return attempts[index]


async def reserve_attempt(
    practice: dict,
    *,
    transcript: str,
    mode: str,
    free_topic: str,
) -> dict:
    practice_id = str(practice["_id"])
    latest = await get_db().practiceAttempts.find_one(
        {"practiceId": practice_id},
        projection={"round": 1},
        sort=[("round", -1)],
    )
    embedded_round = max(
        (int(item.get("round") or index + 1) for index, item in enumerate(practice.get("attempts", []))),
        default=0,
    )
    base = max(
        int(practice.get("attemptSeq") or 0),
        embedded_round,
        int((latest or {}).get("round") or 0),
    )
    await get_db().practiceSessions.update_one(
        {
            **id_filter(practice_id),
            "$or": [
                {"attemptSeq": {"$exists": False}},
                {"attemptSeq": {"$lt": base}},
            ],
        },
        {"$set": {"attemptSeq": base}},
    )
    session = await get_db().practiceSessions.find_one_and_update(
        id_filter(practice_id),
        {"$inc": {"attemptSeq": 1}},
        projection={"attemptSeq": 1},
        return_document=ReturnDocument.AFTER,
    )
    round_no = int(session["attemptSeq"])
    now = datetime.now(timezone.utc)
    attempt = {
        "_id": practice_attempt_id(),
        "practiceId": practice_id,
        "userId": practice["userId"],
        "sourceType": normalize_source_type(practice.get("sourceType")),
        "round": round_no,
        "mode": mode,
        "freeTopic": free_topic if mode == "free" else "",
        "transcript": transcript,
        "status": "evaluating",
        "chat": [],
        "createdAt": now,
        "updatedAt": now,
    }
    await get_db().practiceAttempts.insert_one(attempt)
    return _public_attempt(attempt)


async def complete_attempt(attempt_id: str, result: dict) -> None:
    now = datetime.now(timezone.utc)
    await get_db().practiceAttempts.update_one(
        id_filter(attempt_id),
        {"$set": {
            "summary": result.get("summary", ""),
            "standardAnswer": result.get("standardAnswer", ""),
            "standardAnswerNotes": result.get("standardAnswerNotes", []),
            "note": "",
            "noteChinese": "",
            "score": result.get("score"),
            "gaps": result.get("gaps", []),
            "progress": result.get("progress"),
            "status": "completed",
            "updatedAt": now,
        }},
    )


async def update_attempt(attempt_id: str, update: dict) -> bool:
    """Update an independent Attempt. Returns False for a legacy fallback row."""
    result = await get_db().practiceAttempts.update_one(id_filter(attempt_id), update)
    return result.matched_count > 0


async def discard_attempt(attempt_id: str) -> None:
    await get_db().practiceAttempts.delete_one({**id_filter(attempt_id), "status": "evaluating"})
