"""OSS 业务路径生成器。

路径只由业务归属和稳定 ID 决定，调用方不再自行拼接字符串。
"""

from dataclasses import dataclass
from datetime import datetime


_AUDIO_EXTENSIONS = {"m4a", "mp3", "ogg", "wav", "webm"}
_SPEECH_PURPOSES = {
    "correction",
    "example",
    "other",
    "pronunciation-target",
    "review",
    "standard-answer",
}


@dataclass(frozen=True)
class PracticeAssetContext:
    user_id: str
    created_at: datetime | str
    practice_id: str
    attempt_index: int


def _month(created_at: datetime | str) -> str:
    if isinstance(created_at, datetime):
        return created_at.strftime("%Y%m")
    value = str(created_at or "")
    compact = value.replace("-", "")
    if len(compact) >= 6 and compact[:6].isdigit():
        return compact[:6]
    raise ValueError("created_at must include a year and month")


def _audio_extension(extension: str) -> str:
    normalized = extension.lower().lstrip(".")
    if normalized not in _AUDIO_EXTENSIONS:
        raise ValueError(f"unsupported audio extension: {extension}")
    return normalized


def practice_prefix(user_id: str, created_at: datetime | str, practice_id: str) -> str:
    return f"practiceSessions/{user_id}/{_month(created_at)}/{practice_id}"


def recording_original_key(
    context: PracticeAssetContext,
    recording_id: str,
    extension: str,
) -> str:
    if context.attempt_index < 0:
        raise ValueError("attempt_index must be non-negative")
    prefix = practice_prefix(context.user_id, context.created_at, context.practice_id)
    ext = _audio_extension(extension)
    attempt_number = context.attempt_index + 1
    return f"{prefix}/attempts/{attempt_number}/recordings/{recording_id}/original.{ext}"


def speech_key(
    context: PracticeAssetContext,
    purpose: str,
    audio_id: str,
    extension: str,
) -> str:
    if context.attempt_index < 0:
        raise ValueError("attempt_index must be non-negative")
    if purpose not in _SPEECH_PURPOSES:
        raise ValueError(f"unsupported speech purpose: {purpose}")
    prefix = practice_prefix(context.user_id, context.created_at, context.practice_id)
    ext = _audio_extension(extension)
    attempt_number = context.attempt_index + 1
    return f"{prefix}/attempts/{attempt_number}/speech/{purpose}/{audio_id}.{ext}"


def avatar_key(user_id: str, avatar_id: str, variant: str) -> str:
    if variant not in {"original", "thumbnail"}:
        raise ValueError(f"unsupported avatar variant: {variant}")
    return f"users/{user_id}/profile/avatar/{avatar_id}/{variant}.jpg"
