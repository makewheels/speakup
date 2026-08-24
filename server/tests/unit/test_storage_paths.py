from datetime import datetime, timezone

import pytest

from services.storage_paths import PracticeAssetContext, avatar_key, recording_original_key, speech_key


CREATED_AT = datetime(2026, 8, 24, 8, 30, tzinfo=timezone.utc)
CONTEXT = PracticeAssetContext("u_1", CREATED_AT, "ps_1", 1)


def test_recording_path_groups_by_owner_month_session_and_attempt():
    key = recording_original_key(CONTEXT, "rec_1", "WEBM")

    assert key == (
        "practiceSessions/u_1/202608/ps_1/attempts/2/"
        "recordings/rec_1/original.webm"
    )


def test_speech_path_distinguishes_business_purpose():
    context = PracticeAssetContext("u_1", CREATED_AT, "ps_1", 0)
    correction = speech_key(context, "correction", "tts_a", "wav")
    example = speech_key(context, "example", "tts_a", "wav")

    assert correction.endswith("/attempts/1/speech/correction/tts_a.wav")
    assert example.endswith("/attempts/1/speech/example/tts_a.wav")
    assert correction != example


def test_avatar_path_keeps_versions_and_variants_together():
    assert avatar_key("u_1", "av_1", "thumbnail") == (
        "users/u_1/profile/avatar/av_1/thumbnail.jpg"
    )


@pytest.mark.parametrize("extension", ["pcm", "exe", ""])
def test_storage_paths_reject_raw_or_unknown_audio_extensions(extension):
    with pytest.raises(ValueError):
        recording_original_key(PracticeAssetContext("u_1", CREATED_AT, "ps_1", 0), "rec_1", extension)
