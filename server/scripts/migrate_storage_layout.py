"""把存量练习录音、朗读和头像迁移到业务路径 v2。

默认只审计。`--execute` 才复制对象并切换 MongoDB 引用；再加
`--delete-source` 才会在新对象和引用均校验后删除已迁移旧对象。
"""

import argparse
import hashlib
import mimetypes
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient

from config import MONGO_URI
from services import oss_storage
from services.avatar_images import build_avatar_variants
from services.storage_paths import PracticeAssetContext, avatar_key, recording_original_key, speech_key
from services.tts import speech_asset


@dataclass
class Stats:
    sessions: int = 0
    recordings: int = 0
    speech: int = 0
    avatars: int = 0
    copied: int = 0
    db_updated: int = 0
    deleted: int = 0
    unlinked_legacy: int = 0
    unlinked_categories: dict[str, int] = field(default_factory=dict)
    known_sources: set[str] = field(default_factory=set)


@dataclass
class PracticePlan:
    set_fields: dict[str, object] = field(default_factory=dict)
    add_to_set: dict[str, list[object]] = field(default_factory=dict)
    old_sources: set[str] = field(default_factory=set)
    recording_indexes: set[int] = field(default_factory=set)
    recording_sources: dict[int, str] = field(default_factory=dict)


def _created_at(value: object, entity_id: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(getattr(entity_id, "generation_time", None), datetime):
        return entity_id.generation_time
    entity_text = str(entity_id)
    match = re.search(r"(\d{13})", entity_text)
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000, timezone.utc)
    raise ValueError(f"无法确定 {entity_text} 的创建月份")


def _legacy_id(prefix: str, source_key: str, created_at: datetime) -> str:
    timestamp = re.search(r"(?:^|/)(\d{13})(?:\.|/|$)", source_key)
    millis = timestamp.group(1) if timestamp else str(int(created_at.timestamp() * 1000))
    digest = hashlib.sha1(source_key.encode()).hexdigest()[:10]
    return f"{prefix}{millis}{digest}"


def _recording_source(practice: dict, attempt: dict, attempt_index: int) -> tuple[str, dict]:
    current = attempt.get("recording") or {}
    if current.get("key"):
        return current["key"], current
    if attempt.get("recordingKey"):
        return attempt["recordingKey"], {}
    for item in practice.get("recordings", []):
        if item.get("attemptIndex") == attempt_index and item.get("key"):
            return item["key"], item
    return "", {}


def _extension(source_key: str, metadata: dict) -> str:
    extension = source_key.rsplit(".", 1)[-1].lower() if "." in source_key else ""
    if extension in {"m4a", "mp3", "ogg", "wav", "webm"}:
        return extension
    return metadata.get("format") or "webm"


def _recording_asset(practice: dict, attempt: dict, attempt_index: int) -> tuple[str, dict] | None:
    source, metadata = _recording_source(practice, attempt, attempt_index)
    if not source:
        return None
    created = _created_at(practice.get("createdAt"), practice["_id"])
    extension = _extension(source, metadata)
    recording_id = metadata.get("id") or _legacy_id("rec_", source, created)
    context = PracticeAssetContext(
        user_id=practice["userId"],
        created_at=created,
        practice_id=str(practice["_id"]),
        attempt_index=attempt_index,
    )
    target = recording_original_key(context, recording_id, extension)
    content_type = metadata.get("contentType") or mimetypes.guess_type(f"x.{extension}")[0] or "audio/webm"
    asset = {
        "id": recording_id,
        "key": target,
        "format": extension,
        "contentType": content_type,
        "sizeBytes": metadata.get("sizeBytes", 0),
        "createdAt": metadata.get("createdAt") or attempt.get("createdAt") or created,
    }
    return source, asset


def _speech_candidates(attempt: dict) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    if attempt.get("standardAnswer"):
        candidates.append(("standard-answer", attempt["standardAnswer"]))
    for gap in attempt.get("gaps", []):
        if gap.get("better"):
            candidates.append(("correction", gap["better"]))
        if gap.get("example"):
            candidates.append(("example", gap["example"]))
    for issue in (attempt.get("pronunciation") or {}).get("issues", []):
        if issue.get("word"):
            candidates.append(("pronunciation-target", issue["word"]))
    return list(dict.fromkeys(candidates))


def _copy(source: str, target: str, execute: bool, stats: Stats) -> bool:
    stats.known_sources.add(source)
    if source == target:
        return True
    if not oss_storage.exists(source):
        return False
    if execute:
        info = oss_storage.copy_verified(source, target)
        stats.copied += 1
        return info.size >= 0
    return True


def _delete_sources(sources: set[str], enabled: bool, stats: Stats) -> None:
    if not enabled:
        return
    for key in sorted(sources):
        oss_storage.delete(key)
        stats.deleted += 1


def _plan_recording(
    practice: dict, attempt: dict, index: int, execute: bool, stats: Stats
) -> tuple[str, dict, str] | None:
    planned = _recording_asset(practice, attempt, index)
    if not planned:
        return None
    source, asset = planned
    if source == asset["key"]:
        return None
    if not _copy(source, asset["key"], execute, stats):
        return None
    if execute and not asset["sizeBytes"]:
        asset["sizeBytes"] = oss_storage.object_info(asset["key"]).size
    stats.recordings += 1
    return f"attempts.{index}.recording", asset, source


def _plan_speech(practice: dict, attempt: dict, index: int, execute: bool, stats: Stats) -> list[tuple[dict, str]]:
    practice_id = str(practice["_id"])
    created = _created_at(practice.get("createdAt"), practice["_id"])
    assets: list[tuple[dict, str]] = []
    for purpose, text in _speech_candidates(attempt):
        audio_id, extension, content_type = speech_asset(text)
        legacy_id = audio_id.removeprefix("sp_")
        source = f"practiceSessions/{practice_id}/tts/{legacy_id}.{extension}"
        context = PracticeAssetContext(
            user_id=practice["userId"],
            created_at=created,
            practice_id=practice_id,
            attempt_index=index,
        )
        target = speech_key(context, purpose, audio_id, extension)
        if not _copy(source, target, execute, stats):
            continue
        assets.append(({
            "id": audio_id,
            "key": target,
            "purpose": purpose,
            "format": extension,
            "contentType": content_type,
        }, source))
        stats.speech += 1
    return assets


def _attempt_plan(
    practice: dict, attempt: dict, index: int, execute: bool, stats: Stats
) -> PracticePlan:
    plan = PracticePlan()
    recording = _plan_recording(practice, attempt, index, execute, stats)
    if recording:
        field_name, asset, source = recording
        plan.set_fields[field_name] = asset
        plan.recording_indexes.add(index)
        plan.recording_sources[index] = source
        if source != asset["key"]:
            plan.old_sources.add(source)
    speech_assets = _plan_speech(practice, attempt, index, execute, stats)
    if speech_assets:
        field_name = f"attempts.{index}.speechAssets"
        plan.add_to_set[field_name] = [asset for asset, _ in speech_assets]
        plan.old_sources.update(source for asset, source in speech_assets if source != asset["key"])
    return plan


def _merge_plan(target: PracticePlan, source: PracticePlan) -> None:
    target.set_fields.update(source.set_fields)
    target.recording_indexes.update(source.recording_indexes)
    target.recording_sources.update(source.recording_sources)
    target.old_sources.update(source.old_sources)
    for key, values in source.add_to_set.items():
        target.add_to_set.setdefault(key, []).extend(values)


def _practice_update(practice: dict, plan: PracticePlan) -> dict[str, dict]:
    update: dict[str, dict] = {}
    if plan.set_fields:
        update["$set"] = plan.set_fields
        update["$unset"] = {
            f"attempts.{index}.recordingKey": "" for index in plan.recording_indexes
        }
        legacy_indexes = {
            item.get("attemptIndex") for item in practice.get("recordings", []) if item.get("key")
        }
        if legacy_indexes.issubset(plan.recording_indexes):
            update["$unset"]["recordings"] = ""
    if plan.add_to_set:
        update["$addToSet"] = {
            key: {"$each": values} for key, values in plan.add_to_set.items()
        }
    target_keys = [value["key"] for value in plan.set_fields.values()]
    target_keys.extend(asset["key"] for values in plan.add_to_set.values() for asset in values)
    if plan.old_sources:
        update.setdefault("$set", {})["storageMigrationV2.migratedAt"] = datetime.now(timezone.utc)
        update.setdefault("$addToSet", {})["storageMigrationV2.oldKeys"] = {
            "$each": sorted(plan.old_sources)
        }
        update["$addToSet"]["storageMigrationV2.targetKeys"] = {"$each": sorted(target_keys)}
    return update


def _practice_update_query(practice: dict, plan: PracticePlan) -> dict:
    conditions: list[dict] = [{"_id": practice["_id"]}]
    for index, source in sorted(plan.recording_sources.items()):
        conditions.append({"$or": [
            {f"attempts.{index}.recording.key": source},
            {f"attempts.{index}.recordingKey": source},
            {"recordings": {"$elemMatch": {"attemptIndex": index, "key": source}}},
        ]})
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def migrate_practice(practice: dict, collection, execute: bool, stats: Stats) -> None:
    practice_id = str(practice["_id"])
    stats.known_sources.update((practice.get("storageMigrationV2") or {}).get("oldKeys", []))
    plan = PracticePlan()
    for index, attempt in enumerate(practice.get("attempts", [])):
        _merge_plan(plan, _attempt_plan(practice, attempt, index, execute, stats))
    if not plan.set_fields and not plan.add_to_set:
        return
    stats.sessions += 1
    if not execute:
        return
    result = collection.update_one(
        _practice_update_query(practice, plan),
        _practice_update(practice, plan),
    )
    if result.matched_count == 0:
        raise RuntimeError(f"练习在迁移时已被修改，请重新运行: {practice_id}")
    refreshed = collection.find_one({"_id": practice["_id"]}, {"attempts": 1})
    for index in plan.recording_indexes:
        expected = plan.set_fields[f"attempts.{index}.recording"]["key"]
        if refreshed["attempts"][index]["recording"]["key"] != expected:
            raise RuntimeError(f"录音引用校验失败: {practice_id} attempt={index + 1}")
    stats.db_updated += 1


def migrate_avatar(user: dict, collection, execute: bool, stats: Stats) -> None:
    stats.known_sources.update((user.get("storageMigrationV2") or {}).get("oldKeys", []))
    current = user.get("avatar") or {}
    if current.get("originalKey") and current.get("thumbnailKey"):
        return
    source = user.get("avatarKey")
    if not source:
        return
    stats.known_sources.add(source)
    stats.avatars += 1
    if not execute:
        return
    data = oss_storage.download_bytes(source)
    variants = build_avatar_variants(data)
    created = _created_at(user.get("createdAt"), user["_id"])
    asset_id = _legacy_id("av_", source, created)
    original_key = avatar_key(str(user["_id"]), asset_id, "original")
    thumbnail_key = avatar_key(str(user["_id"]), asset_id, "thumbnail")
    oss_storage.upload_bytes(original_key, variants.original, "image/jpeg")
    oss_storage.upload_bytes(thumbnail_key, variants.thumbnail, "image/jpeg")
    if oss_storage.download_bytes(original_key) != variants.original:
        raise RuntimeError(f"头像主图校验失败: {user['_id']}")
    if oss_storage.download_bytes(thumbnail_key) != variants.thumbnail:
        raise RuntimeError(f"头像缩略图校验失败: {user['_id']}")
    avatar = {
        "id": asset_id,
        "originalKey": original_key,
        "thumbnailKey": thumbnail_key,
        "contentType": "image/jpeg",
        "originalSize": variants.original_size,
        "thumbnailSize": variants.thumbnail_size,
        "createdAt": datetime.now(timezone.utc),
    }
    result = collection.update_one(
        {"_id": user["_id"], "avatarKey": source, "avatar": {"$exists": False}},
        {
            "$set": {
                "avatar": avatar,
                "storageMigrationV2.migratedAt": datetime.now(timezone.utc),
            },
            "$addToSet": {
                "storageMigrationV2.oldKeys": source,
                "storageMigrationV2.targetKeys": {"$each": [original_key, thumbnail_key]},
            },
            "$unset": {"avatarKey": ""},
        },
    )
    if result.matched_count == 0:
        raise RuntimeError(f"头像在迁移时已被修改，请重新运行: {user['_id']}")
    refreshed = collection.find_one({"_id": user["_id"]}, {"avatar": 1})
    if (refreshed.get("avatar") or {}).get("thumbnailKey") != thumbnail_key:
        raise RuntimeError(f"头像引用校验失败: {user['_id']}")
    stats.db_updated += 1


def _document_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = {value["key"]} if isinstance(value.get("key"), str) else set()
        if isinstance(value.get("originalKey"), str):
            keys.add(value["originalKey"])
        if isinstance(value.get("thumbnailKey"), str):
            keys.add(value["thumbnailKey"])
        for child in value.values():
            keys.update(_document_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(_document_keys(child))
        return keys
    return set()


def cleanup_ledgers(collection, stats: Stats) -> None:
    for document in collection.find({"storageMigrationV2.oldKeys.0": {"$exists": True}}):
        ledger = document["storageMigrationV2"]
        targets = set(ledger.get("targetKeys", []))
        if not targets.issubset(_document_keys(document)):
            raise RuntimeError(f"数据库目标引用不完整，拒绝清理: {document['_id']}")
        for key in targets:
            oss_storage.object_info(key)
        _delete_sources(set(ledger.get("oldKeys", [])), True, stats)
        collection.update_one(
            {"_id": document["_id"]},
            {"$unset": {"storageMigrationV2": ""}},
        )


def _mark_unlinked(stats: Stats, category: str) -> None:
    stats.unlinked_legacy += 1
    stats.unlinked_categories[category] = stats.unlinked_categories.get(category, 0) + 1


def _audit_practice_objects(stats: Stats) -> None:
    for item in oss_storage.iter_objects("practiceSessions/"):
        if item.key in stats.known_sources:
            continue
        if "/recording/" in item.key:
            _mark_unlinked(stats, "practice-recording")
        elif re.search(r"^practiceSessions/[^/]+/tts/", item.key):
            _mark_unlinked(stats, "practice-speech")


def _audit_prefix(stats: Stats, prefix: str, category: str, suffix: str = "") -> None:
    for item in oss_storage.iter_objects(prefix):
        if suffix and not item.key.endswith(suffix):
            continue
        if item.key not in stats.known_sources:
            _mark_unlinked(stats, category)


def audit_unlinked_objects(stats: Stats) -> None:
    _audit_practice_objects(stats)
    _audit_prefix(stats, "users/", "avatar", "/avatar/current")
    _audit_prefix(stats, "recordings/", "global-recording")
    _audit_prefix(stats, "tts/", "global-speech")


def main(execute: bool, delete_source: bool) -> None:
    if delete_source and not execute:
        raise SystemExit("--delete-source 必须与 --execute 一起使用")
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    stats = Stats()
    try:
        if delete_source:
            for collection in (db.practiceSessions, db.users):
                for document in collection.find(
                    {"storageMigrationV2.oldKeys.0": {"$exists": True}},
                    {"storageMigrationV2.oldKeys": 1},
                ):
                    stats.known_sources.update(document["storageMigrationV2"]["oldKeys"])
            cleanup_ledgers(db.practiceSessions, stats)
            cleanup_ledgers(db.users, stats)
        else:
            for practice in db.practiceSessions.find(
                {"$or": [
                    {"attempts.recordingKey": {"$exists": True}},
                    {"recordings.0": {"$exists": True}},
                    {"attempts.0": {"$exists": True}},
                ]}
            ):
                migrate_practice(practice, db.practiceSessions, execute, stats)
            for user in db.users.find({"avatarKey": {"$exists": True}}):
                migrate_avatar(user, db.users, execute, stats)
        audit_unlinked_objects(stats)
    finally:
        client.close()
    mode = "执行" if execute else "审计"
    print(f"storage-v2 {mode}完成")
    print(f"sessions={stats.sessions} recordings={stats.recordings} speech={stats.speech} avatars={stats.avatars}")
    print(f"copied={stats.copied} dbUpdated={stats.db_updated} deleted={stats.deleted}")
    print(f"unlinkedLegacy={stats.unlinked_legacy}")
    if stats.unlinked_categories:
        summary = " ".join(
            f"{category}={count}" for category, count in sorted(stats.unlinked_categories.items())
        )
        print(f"unlinkedByCategory {summary}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="复制对象并切换数据库引用")
    parser.add_argument("--delete-source", action="store_true", help="校验通过后删除已迁移旧对象")
    args = parser.parse_args()
    main(args.execute, args.delete_source)
