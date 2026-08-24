from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId

from scripts.migrate_storage_layout import (
    Stats,
    _document_keys,
    _created_at,
    _legacy_id,
    _recording_asset,
    _speech_candidates,
    cleanup_ledgers,
)
from scripts.migrate_attempt_entities import (
    MigrationContext,
    Stats as AttemptStats,
    _business_digest,
    _recording_asset as attempt_recording_asset,
)
from scripts.storage_orphan_cleanup import managed_category


CREATED = datetime(2026, 8, 24, tzinfo=timezone.utc)


def test_legacy_recording_gets_deterministic_id_and_business_path():
    practice = {
        "_id": "ps_1787550000000aaaaaaaaaa",
        "userId": "u_1",
        "createdAt": CREATED,
        "recordings": [{
            "key": "practiceSessions/u_1/202608/ps_1/recording/1787551234567.webm",
            "attemptIndex": 0,
        }],
    }

    first = _recording_asset(practice, {}, 0)
    second = _recording_asset(practice, {}, 0)

    assert first == second
    source, asset = first
    assert source.endswith("/recording/1787551234567.webm")
    assert asset["id"].startswith("rec_1787551234567")
    assert "/attempts/pa_" in asset["key"]
    assert asset["key"].endswith(f"/recordings/{asset['id']}/original.webm")


def test_speech_candidates_keep_examples_separate_and_deduplicate():
    attempt = {
        "standardAnswer": "A",
        "gaps": [
            {"better": "B", "example": "C"},
            {"better": "B", "example": "C"},
        ],
        "pronunciation": {"issues": [{"word": "three"}]},
    }

    assert _speech_candidates(attempt) == [
        ("standard-answer", "A"),
        ("correction", "B"),
        ("example", "C"),
        ("pronunciation-target", "three"),
    ]


def test_document_keys_collects_nested_recording_speech_and_avatar_keys():
    assert _document_keys({
        "attempts": [{"recording": {"key": "rec"}, "speechAssets": [{"key": "speech"}]}],
        "avatar": {"originalKey": "original", "thumbnailKey": "thumbnail"},
    }) == {"rec", "speech", "original", "thumbnail"}


def test_cleanup_refuses_to_delete_when_database_no_longer_references_target(monkeypatch):
    document = {
        "_id": "ps_1",
        "attempts": [],
        "storageMigrationV2": {"oldKeys": ["old"], "targetKeys": ["target"]},
    }

    class Collection:
        def find(self, query):
            return [document]

    deleted = []
    monkeypatch.setattr("services.oss_storage.delete", deleted.append)

    with pytest.raises(RuntimeError, match="数据库目标引用不完整"):
        cleanup_ledgers(Collection(), Stats())
    assert deleted == []


def test_legacy_id_is_stable_when_filename_has_no_timestamp():
    assert _legacy_id("av_", "users/u_1/avatar/current", CREATED) == _legacy_id(
        "av_", "users/u_1/avatar/current", CREATED
    )


def test_historical_object_id_supplies_missing_created_month():
    oid = ObjectId()
    assert _created_at(None, oid) == oid.generation_time


def test_attempt_v3_recording_path_uses_the_given_stable_attempt_id(monkeypatch):
    practice = {
        "_id": "ps_1787550000000aaaaaaaaaa",
        "userId": "u_1",
        "createdAt": CREATED,
        "recordings": [{"key": "recordings/old.webm", "attemptIndex": 0}],
    }
    monkeypatch.setattr("services.oss_storage.exists", lambda key: True)
    monkeypatch.setattr("services.oss_storage.object_info", lambda key: SimpleNamespace(size=9))
    asset, source = attempt_recording_asset(
        practice,
        {},
        0,
        "pa_1787550000000bbbbbbbbbb",
        MigrationContext(execute=False, stats=AttemptStats()),
    )

    assert source == "recordings/old.webm"
    assert asset["key"].startswith(
        "practiceSessions/u_1/202608/ps_1787550000000aaaaaaaaaa/"
        "attempts/pa_1787550000000bbbbbbbbbb/recordings/"
    )


def test_attempt_business_digest_normalizes_missing_empty_lists():
    embedded = {"round": 1, "transcript": "hello"}
    independent = {
        "round": 1,
        "transcript": "hello",
        "gaps": [],
        "chat": [],
        "standardAnswerNotes": [],
    }
    assert _business_digest(embedded) == _business_digest(independent)


def test_managed_category_marks_numeric_attempt_and_old_roots_as_legacy():
    assert managed_category("recordings/old.webm") == "legacy-recording-root"
    assert managed_category("tts/old.wav") == "legacy-speech-root"
    assert managed_category(
        "practiceSessions/u_1/202608/ps_1/attempts/1/recordings/rec_1/original.webm"
    ) == "legacy-practice-path"
    assert managed_category(
        "practiceSessions/u_1/202608/ps_1/attempts/pa_1/recordings/rec_1/original.webm"
    ) == "attempt-v3"
