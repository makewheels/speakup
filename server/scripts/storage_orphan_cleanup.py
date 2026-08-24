"""Reference audit and guarded cleanup for managed OSS business prefixes."""

import time

from services import oss_storage


MANAGED_PREFIXES = ("practiceSessions/", "recordings/", "tts/", "users/", "feedbacks/")
ORPHAN_GRACE_SECONDS = 3600


def document_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys: set[str] = set()
        for name, child in value.items():
            if name in {"key", "imageKey", "videoKey", "recordingKey", "avatarKey", "originalKey", "thumbnailKey"}:
                if isinstance(child, str) and child:
                    keys.add(child)
            keys.update(document_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(document_keys(child))
        return keys
    return set()


def referenced_keys(db) -> set[str]:
    referenced: set[str] = set()
    for name in ("practiceSessions", "practiceAttempts", "users", "feedbacks", "scenarios"):
        for document in db[name].find({}):
            referenced.update(document_keys(document))
    return referenced


def managed_category(key: str) -> str:
    if key.startswith("recordings/"):
        return "legacy-recording-root"
    if key.startswith("tts/"):
        return "legacy-speech-root"
    if key.startswith("practiceSessions/"):
        parts = key.split("/")
        valid = (
            len(parts) >= 8
            and parts[1].startswith("u_")
            and len(parts[2]) == 6
            and parts[2].isdigit()
            and parts[3].startswith("ps_")
            and parts[4] == "attempts"
            and parts[5].startswith("pa_")
            and parts[6] in {"recordings", "speech"}
        )
        return "attempt-v3" if valid else "legacy-practice-path"
    if key.startswith("users/"):
        return "user-asset"
    if key.startswith("feedbacks/"):
        return "feedback-asset"
    return "unmanaged"


def orphan_objects(referenced: set[str]) -> list[oss_storage.ObjectInfo]:
    objects: dict[str, oss_storage.ObjectInfo] = {}
    for prefix in MANAGED_PREFIXES:
        for item in oss_storage.iter_objects(prefix):
            if item.key not in referenced:
                objects[item.key] = item
    return list(objects.values())


def audit_orphans(db, *, cleanup: bool, stats) -> None:
    referenced = referenced_keys(db)
    now = int(time.time())
    for key in referenced:
        if key.startswith(MANAGED_PREFIXES) and managed_category(key).startswith("legacy"):
            stats.wrong_referenced += 1
    for item in orphan_objects(referenced):
        category = managed_category(item.key)
        stats.orphan_objects += 1
        stats.orphan_categories[category] = stats.orphan_categories.get(category, 0) + 1
        modified = item.last_modified or 0
        if cleanup and modified and now - modified < ORPHAN_GRACE_SECONDS:
            stats.recent_orphans += 1
            continue
        if cleanup:
            oss_storage.delete(item.key)
            stats.deleted += 1
            stats.deleted_bytes += item.size
