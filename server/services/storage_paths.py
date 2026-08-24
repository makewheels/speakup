"""OSS 业务路径生成器。

路径只由业务归属和稳定 ID 决定，调用方不再自行拼接字符串。
"""

from dataclasses import dataclass
from datetime import datetime


_AUDIO_EXTENSIONS = {"m4a", "mp3", "ogg", "wav", "webm"}
_FEEDBACK_IMAGE_EXTENSIONS = {"gif", "heic", "heif", "jpg", "png", "webp"}
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
    attempt_id: str


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
    if not context.attempt_id.startswith("pa_"):
        raise ValueError("attempt_id must be a practice Attempt id")
    prefix = practice_prefix(context.user_id, context.created_at, context.practice_id)
    ext = _audio_extension(extension)
    return f"{prefix}/attempts/{context.attempt_id}/recordings/{recording_id}/original.{ext}"


def speech_key(
    context: PracticeAssetContext,
    purpose: str,
    audio_id: str,
    extension: str,
) -> str:
    if not context.attempt_id.startswith("pa_"):
        raise ValueError("attempt_id must be a practice Attempt id")
    if purpose not in _SPEECH_PURPOSES:
        raise ValueError(f"unsupported speech purpose: {purpose}")
    prefix = practice_prefix(context.user_id, context.created_at, context.practice_id)
    ext = _audio_extension(extension)
    return f"{prefix}/attempts/{context.attempt_id}/speech/{purpose}/{audio_id}.{ext}"


def avatar_key(user_id: str, avatar_id: str, variant: str) -> str:
    if variant not in {"original", "thumbnail"}:
        raise ValueError(f"unsupported avatar variant: {variant}")
    return f"users/{user_id}/profile/avatar/{avatar_id}/{variant}.jpg"


def feedback_image_key(
    user_id: str,
    created_at: datetime | str,
    feedback_id: str,
    image_id: str,
    extension: str,
) -> str:
    ext = extension.lower().lstrip(".")
    if ext not in _FEEDBACK_IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported feedback image extension: {extension}")
    return f"feedbacks/{user_id}/{_month(created_at)}/{feedback_id}/images/{image_id}/original.{ext}"
