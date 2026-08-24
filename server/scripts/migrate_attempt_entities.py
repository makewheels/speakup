"""Migrate embedded Attempts and their assets to the independent v3 layout.

The command is intentionally staged:

* default: audit only;
* ``--execute``: copy verified objects and upsert ``practiceAttempts``;
* ``--execute --delete-source``: verify the independent rows, remove embedded
  rows, then delete unreferenced managed objects older than the safety window.
"""

import argparse
import json
import mimetypes
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient

from config import MONGO_URI
from scripts.storage_orphan_cleanup import (
    audit_orphans,
    document_keys,
    orphan_objects,
    referenced_keys,
)
from services import oss_storage
from services.practice_attempts import legacy_attempt_id
from services.storage_paths import PracticeAssetContext, recording_original_key, speech_key
from services.tts import speech_asset
from utils.data_source import normalize_source_type


BUSINESS_FIELDS = (
    "transcript", "round", "mode", "freeTopic", "summary", "standardAnswer",
    "standardAnswerNotes", "note", "noteChinese", "score", "gaps", "progress", "chat",
)


@dataclass
class Stats:
    sessions: int = 0
    embedded_attempts: int = 0
    independent_attempts: int = 0
    upserted_attempts: int = 0
    linked_documents: int = 0
    recordings: int = 0
    speech: int = 0
    copied: int = 0
    planned_bytes: int = 0
    verified_bytes: int = 0
    deleted: int = 0
    deleted_bytes: int = 0
    missing_objects: int = 0
    conflicts: int = 0
    orphan_objects: int = 0
    recent_orphans: int = 0
    remaining_orphans: int = 0
    wrong_referenced: int = 0
    orphan_categories: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MigrationContext:
    execute: bool
    stats: Stats


def _created_at(value: object, entity_id: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    generation_time = getattr(entity_id, "generation_time", None)
    if isinstance(generation_time, datetime):
        return generation_time
    match = re.search(r"(\d{13})", str(entity_id))
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000, timezone.utc)
    raise ValueError(f"无法确定 {entity_id} 的创建月份")


def _legacy_asset_id(prefix: str, source_key: str, created_at: datetime) -> str:
    import hashlib

    timestamp = re.search(r"(?:^|/)(\d{13})(?:\.|/|$)", source_key)
    millis = timestamp.group(1) if timestamp else str(int(created_at.timestamp() * 1000))
    digest = hashlib.sha1(source_key.encode()).hexdigest()[:10]
    return f"{prefix}{millis}{digest}"


def _recording_source(practice: dict, attempt: dict, index: int) -> tuple[str, dict]:
    current = attempt.get("recording") or {}
    if current.get("key"):
        return current["key"], current
    if attempt.get("recordingKey"):
        return attempt["recordingKey"], {}
    for item in practice.get("recordings", []):
        if item.get("attemptIndex") == index and item.get("key"):
            return item["key"], item
    return "", {}


def _audio_extension(source: str, metadata: dict) -> str:
    extension = source.rsplit(".", 1)[-1].lower() if "." in source else ""
    return extension if extension in {"m4a", "mp3", "ogg", "wav", "webm"} else metadata.get("format", "webm")


def _copy(source: str, target: str, *, execute: bool, stats: Stats) -> None:
    if source == target:
        if not oss_storage.exists(target):
            stats.missing_objects += 1
            if execute:
                raise RuntimeError(f"数据库引用的 OSS 对象不存在: {target}")
        else:
            stats.planned_bytes += oss_storage.object_info(target).size
        return
    if not oss_storage.exists(source):
        stats.missing_objects += 1
        if execute:
            raise RuntimeError(f"待迁移 OSS 对象不存在: {source}")
        return
    stats.planned_bytes += oss_storage.object_info(source).size
    if execute:
        target_info = oss_storage.copy_verified(source, target)
        stats.copied += 1
        stats.verified_bytes += target_info.size


def _recording_asset(
    practice: dict,
    attempt: dict,
    index: int,
    attempt_id: str,
    context: MigrationContext,
) -> tuple[dict | None, str]:
    source, metadata = _recording_source(practice, attempt, index)
    if not source:
        return None, ""
    created = _created_at(practice.get("createdAt"), practice["_id"])
    extension = _audio_extension(source, metadata)
    asset_id = metadata.get("id") or _legacy_asset_id("rec_", source, created)
    storage_context = PracticeAssetContext(
        user_id=practice["userId"],
        created_at=created,
        practice_id=str(practice["_id"]),
        attempt_id=attempt_id,
    )
    target = recording_original_key(storage_context, asset_id, extension)
    _copy(source, target, execute=context.execute, stats=context.stats)
    size = metadata.get("sizeBytes", 0)
    if context.execute and not size:
        size = oss_storage.object_info(target).size
    context.stats.recordings += 1
    return {
        "id": asset_id,
        "key": target,
        "format": extension,
        "contentType": metadata.get("contentType")
        or mimetypes.guess_type(f"x.{extension}")[0]
        or "audio/webm",
        "sizeBytes": size,
        "createdAt": metadata.get("createdAt") or attempt.get("createdAt") or created,
    }, source


def _speech_candidates(attempt: dict) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    if attempt.get("standardAnswer"):
        candidates.append(("standard-answer", attempt["standardAnswer"]))
    for gap in attempt.get("gaps", []):
        if gap.get("better"):
            candidates.append(("correction", gap["better"]))
        if gap.get("example"):
            candidates.append(("example", gap["example"]))
    return list(dict.fromkeys(candidates))


def _speech_assets(
    practice: dict,
    attempt: dict,
    attempt_id: str,
    *,
    execute: bool,
    stats: Stats,
) -> tuple[list[dict], set[str]]:
    practice_id = str(practice["_id"])
    created = _created_at(practice.get("createdAt"), practice["_id"])
    context = PracticeAssetContext(practice["userId"], created, practice_id, attempt_id)
    planned: dict[tuple[str, str], tuple[str, dict]] = {}
    for asset in attempt.get("speechAssets", []):
        source = asset.get("key", "")
        if not source:
            continue
        purpose = asset.get("purpose") or "other"
        extension = _audio_extension(source, asset)
        audio_id = asset.get("id") or _legacy_asset_id("sp_", source, created)
        planned[(purpose, audio_id)] = (source, {
            **asset,
            "id": audio_id,
            "key": speech_key(context, purpose, audio_id, extension),
            "purpose": purpose,
            "format": extension,
        })
    for purpose, text in _speech_candidates(attempt):
        audio_id, extension, content_type = speech_asset(text)
        if (purpose, audio_id) in planned:
            continue
        legacy_hash = audio_id.removeprefix("sp_")
        candidates = (
            f"practiceSessions/{practice_id}/tts/{legacy_hash}.{extension}",
            f"tts/{legacy_hash}.{extension}",
        )
        source = next((key for key in candidates if oss_storage.exists(key)), "")
        if source:
            planned[(purpose, audio_id)] = (source, {
                "id": audio_id,
                "key": speech_key(context, purpose, audio_id, extension),
                "purpose": purpose,
                "format": extension,
                "contentType": content_type,
            })
    assets: list[dict] = []
    sources: set[str] = set()
    for source, asset in planned.values():
        _copy(source, asset["key"], execute=execute, stats=stats)
        assets.append(asset)
        sources.add(source)
        stats.speech += 1
    return assets, sources


def _attempt_document(
    practice: dict,
    embedded: dict,
    index: int,
    attempt_id: str,
    context: MigrationContext,
) -> tuple[dict, set[str], set[str]]:
    round_no = int(embedded.get("round") or index + 1)
    created = embedded.get("createdAt") or practice.get("createdAt") or datetime.now(timezone.utc)
    doc = {key: value for key, value in embedded.items() if key not in {"_id", "attemptId", "recordingKey"}}
    doc.update({
        "_id": attempt_id,
        "practiceId": str(practice["_id"]),
        "userId": practice["userId"],
        "sourceType": normalize_source_type(practice.get("sourceType")),
        "round": round_no,
        "status": "completed",
        "createdAt": created,
        "updatedAt": embedded.get("updatedAt") or created,
    })
    recording, recording_source = _recording_asset(
        practice, embedded, index, attempt_id, context,
    )
    if recording:
        doc["recording"] = recording
    speech_assets, speech_sources = _speech_assets(
        practice,
        embedded,
        attempt_id,
        execute=context.execute,
        stats=context.stats,
    )
    if speech_assets:
        doc["speechAssets"] = speech_assets
    sources = speech_sources | ({recording_source} if recording_source else set())
    targets = {item["key"] for item in speech_assets}
    if recording:
        targets.add(recording["key"])
    return doc, sources - targets, targets


def _business_digest(value: dict) -> str:
    list_fields = {"standardAnswerNotes", "gaps", "chat"}
    string_fields = {
        "transcript", "mode", "freeTopic", "summary", "standardAnswer", "note", "noteChinese",
    }
    payload = {}
    for field in BUSINESS_FIELDS:
        default = [] if field in list_fields else "" if field in string_fields else None
        payload[field] = value.get(field, default)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def _link_attempt_documents(db, practice_id: str, index: int, attempt_id: str, stats: Stats) -> None:
    filters = {"practiceId": practice_id, "attemptIndex": index}
    for collection in (db.feedbacks, db.reviewItems):
        result = collection.update_many(filters, {"$set": {"attemptId": attempt_id}})
        stats.linked_documents += result.modified_count
    result = db.llmCalls.update_many(
        {"linkedTo.sessionId": practice_id, "linkedTo.attemptIndex": index},
        {"$set": {"linkedTo.attemptId": attempt_id}},
    )
    stats.linked_documents += result.modified_count


def migrate_session(practice: dict, db, *, execute: bool, stats: Stats) -> None:
    embedded_attempts = practice.get("attempts", [])
    if not embedded_attempts:
        return
    stats.sessions += 1
    context = MigrationContext(execute=execute, stats=stats)
    old_sources: set[str] = set()
    target_keys: set[str] = set()
    mappings: list[dict] = []
    for index, embedded in enumerate(embedded_attempts):
        stats.embedded_attempts += 1
        round_no = int(embedded.get("round") or index + 1)
        existing = db.practiceAttempts.find_one({
            "practiceId": str(practice["_id"]), "round": round_no,
        })
        attempt_id = str(existing["_id"]) if existing else legacy_attempt_id(practice, embedded, round_no)
        if existing:
            stats.independent_attempts += 1
            if _business_digest(existing) != _business_digest({**embedded, "round": round_no}):
                stats.conflicts += 1
                if execute:
                    raise RuntimeError(f"Attempt 业务字段冲突: {practice['_id']} round={round_no}")
        doc, sources, targets = _attempt_document(
            practice, embedded, index, attempt_id, context,
        )
        old_sources.update(sources)
        target_keys.update(targets)
        mappings.append({"round": round_no, "attemptId": attempt_id})
        if execute:
            values = {key: value for key, value in doc.items() if key != "_id"}
            db.practiceAttempts.update_one(
                {"_id": attempt_id},
                {"$set": values, "$setOnInsert": {"_id": attempt_id}},
                upsert=True,
            )
            _link_attempt_documents(db, str(practice["_id"]), index, attempt_id, stats)
            stats.upserted_attempts += 1
    if execute:
        db.practiceSessions.update_one(
            {"_id": practice["_id"]},
            {
                "$max": {"attemptSeq": max(item["round"] for item in mappings)},
                "$set": {
                    "attemptMigrationV3": {
                        "mappings": mappings,
                        "oldKeys": sorted(old_sources),
                        "targetKeys": sorted(target_keys),
                        "migratedAt": datetime.now(timezone.utc),
                    },
                },
            },
        )


def cleanup_sessions(db, stats: Stats) -> None:
    for practice in db.practiceSessions.find({"attempts.0": {"$exists": True}}):
        mappings = (practice.get("attemptMigrationV3") or {}).get("mappings", [])
        if len(mappings) != len(practice.get("attempts", [])):
            raise RuntimeError(f"Attempt 映射数量不一致: {practice['_id']}")
        for index, embedded in enumerate(practice["attempts"]):
            mapping = mappings[index]
            independent = db.practiceAttempts.find_one({"_id": mapping["attemptId"]})
            if not independent or _business_digest(independent) != _business_digest({
                **embedded, "round": mapping["round"],
            }):
                raise RuntimeError(f"Attempt 清理前复验失败: {practice['_id']} round={index + 1}")
            for key in document_keys(independent):
                oss_storage.object_info(key)
        db.practiceSessions.update_one(
            {"_id": practice["_id"]},
            {
                "$unset": {"attempts": "", "recordings": ""},
                "$set": {"attemptMigrationV3.cleanedAt": datetime.now(timezone.utc)},
            },
        )


def main(*, execute: bool, delete_source: bool) -> Stats:
    if delete_source and not execute:
        raise SystemExit("--delete-source 必须与 --execute 一起使用")
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    stats = Stats()
    try:
        for practice in db.practiceSessions.find({"attempts.0": {"$exists": True}}):
            migrate_session(practice, db, execute=execute, stats=stats)
        if delete_source:
            cleanup_sessions(db, stats)
        audit_orphans(db, cleanup=delete_source, stats=stats)
        if delete_source:
            remaining_embedded = db.practiceSessions.count_documents({"attempts.0": {"$exists": True}})
            stats.remaining_orphans = len(orphan_objects(referenced_keys(db)))
            if remaining_embedded or stats.wrong_referenced or stats.remaining_orphans:
                raise RuntimeError(
                    f"cleanup 未收口: embedded={remaining_embedded} "
                    f"wrongReferenced={stats.wrong_referenced} "
                    f"remainingOrphans={stats.remaining_orphans}"
                )
    finally:
        client.close()
    mode = "cleanup" if delete_source else "migrate" if execute else "audit"
    print(f"attempt-storage-v3 mode={mode}")
    print(
        f"sessions={stats.sessions} embeddedAttempts={stats.embedded_attempts} "
        f"independentExisting={stats.independent_attempts} upserted={stats.upserted_attempts} "
        f"linkedDocuments={stats.linked_documents}"
    )
    print(
        f"recordings={stats.recordings} speech={stats.speech} copied={stats.copied} "
        f"plannedBytes={stats.planned_bytes} verifiedBytes={stats.verified_bytes} "
        f"missingObjects={stats.missing_objects} conflicts={stats.conflicts}"
    )
    print(
        f"orphanObjects={stats.orphan_objects} recentOrphans={stats.recent_orphans} "
        f"remainingOrphans={stats.remaining_orphans} "
        f"deleted={stats.deleted} deletedBytes={stats.deleted_bytes} "
        f"wrongReferenced={stats.wrong_referenced}"
    )
    if stats.orphan_categories:
        print("orphanByCategory " + " ".join(
            f"{key}={value}" for key, value in sorted(stats.orphan_categories.items())
        ))
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="复制对象并切换数据库引用")
    parser.add_argument("--delete-source", action="store_true", help="复验后清理旧结构和无引用对象")
    arguments = parser.parse_args()
    main(execute=arguments.execute, delete_source=arguments.delete_source)
