from datetime import datetime, timezone

import pytest

from services.storage_paths import (
    PracticeAssetContext,
    avatar_key,
    feedback_image_key,
    recording_original_key,
    speech_key,
)


CREATED_AT = datetime(2026, 8, 24, 8, 30, tzinfo=timezone.utc)
CONTEXT = PracticeAssetContext("u_1", CREATED_AT, "ps_1", "pa_1")


def test_recording_path_groups_by_owner_month_session_and_attempt():
    key = recording_original_key(CONTEXT, "rec_1", "WEBM")

    assert key == (
        "practiceSessions/u_1/202608/ps_1/attempts/pa_1/"
        "recordings/rec_1/original.webm"
    )


def test_speech_path_distinguishes_business_purpose():
    context = PracticeAssetContext("u_1", CREATED_AT, "ps_1", "pa_1")
    correction = speech_key(context, "correction", "tts_a", "wav")
    example = speech_key(context, "example", "tts_a", "wav")

    assert correction.endswith("/attempts/pa_1/speech/correction/tts_a.wav")
    assert example.endswith("/attempts/pa_1/speech/example/tts_a.wav")
    assert correction != example


def test_avatar_path_keeps_versions_and_variants_together():
    assert avatar_key("u_1", "av_1", "thumbnail") == (
        "users/u_1/profile/avatar/av_1/thumbnail.jpg"
    )


def test_feedback_image_path_groups_by_owner_month_feedback_and_asset():
    assert feedback_image_key("u_1", CREATED_AT, "fb_1", "fi_1", "PNG") == (
        "feedbacks/u_1/202608/fb_1/images/fi_1/original.png"
    )


@pytest.mark.parametrize("extension", ["pcm", "exe", ""])
def test_storage_paths_reject_raw_or_unknown_audio_extensions(extension):
    with pytest.raises(ValueError):
        recording_original_key(
            PracticeAssetContext("u_1", CREATED_AT, "ps_1", "pa_1"),
            "rec_1",
            extension,
        )


def test_attempt_path_requires_stable_attempt_id():
    with pytest.raises(ValueError, match="attempt_id"):
        recording_original_key(
            PracticeAssetContext("u_1", CREATED_AT, "ps_1", "1"),
            "rec_1",
            "webm",
        )


@pytest.mark.parametrize("created_at", [
    "2026-08-13 17:24:36.826000",
    "2026-08-13T17:24:36+00:00",
    "20260813172436",
])
def test_month_accepts_string_created_at(created_at):
    key = recording_original_key(
        PracticeAssetContext("u_1", created_at, "ps_1", "pa_1"), "rec_1", "webm",
    )

    assert "/202608/" in key


@pytest.mark.parametrize("created_at", ["", "2026", "abcdefgh", None])
def test_month_rejects_values_without_year_month(created_at):
    with pytest.raises(ValueError, match="year and month"):
        recording_original_key(
            PracticeAssetContext("u_1", created_at, "ps_1", "pa_1"), "rec_1", "webm",
        )


def test_speech_path_rejects_unknown_purpose():
    with pytest.raises(ValueError, match="purpose"):
        speech_key(CONTEXT, "karaoke", "tts_a", "wav")


def test_avatar_key_rejects_unknown_variant():
    with pytest.raises(ValueError, match="variant"):
        avatar_key("u_1", "av_1", "medium")


def test_feedback_image_rejects_unknown_extension():
    with pytest.raises(ValueError, match="extension"):
        feedback_image_key("u_1", CREATED_AT, "fb_1", "fi_1", "exe")
