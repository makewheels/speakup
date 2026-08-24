import base64
import hashlib
import hmac
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock

import pytest

from services import pronunciation


def _configure(monkeypatch):
    monkeypatch.setattr(pronunciation, "PRONUNCIATION_ENABLED", True)
    monkeypatch.setattr(pronunciation, "PRONUNCIATION_PROVIDER", "tencent")
    monkeypatch.setattr(pronunciation, "PRONUNCIATION_APP_ID", "123456")
    monkeypatch.setattr(pronunciation, "PRONUNCIATION_SECRET_ID", "secret-id")
    monkeypatch.setattr(pronunciation, "PRONUNCIATION_SECRET_KEY", "secret-key")


def test_build_signed_url_uses_unencoded_sorted_query_for_hmac(monkeypatch):
    _configure(monkeypatch)
    url = pronunciation.build_signed_url(
        "{::cmd{F_IPA=true}} happy", 4, timestamp=100, nonce=7, voice_id="voice-1"
    )
    parsed = urlparse(url)
    params = {key: value[0] for key, value in parse_qs(parsed.query).items()}
    signature = params.pop("signature")
    raw_query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    raw = f"soe.cloud.tencent.com/soe/api/123456?{raw_query}"
    expected = base64.b64encode(hmac.new(b"secret-key", raw.encode(), hashlib.sha1).digest()).decode()
    assert signature == expected
    assert params["ref_text"] == "{::cmd{F_IPA=true}} happy"


@pytest.mark.asyncio
async def test_evaluate_pronunciation_runs_sentence_then_word_detail(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(pronunciation, "PRONUNCIATION_ISSUE_THRESHOLD", 80)
    monkeypatch.setattr(pronunciation, "_wav", AsyncMock(side_effect=[b"full", b"clip"]))
    first = {
        "SuggestedScore": 0.82,
        "PronAccuracy": 0.73,
        "PronFluency": 0.8,
        "PronCompletion": 1,
        "Words": [{"Word": "happy", "PronAccuracy": 62, "MemBeginTime": 200, "MemEndTime": 650, "MatchTag": 0}],
    }
    detail = {
        "Words": [{
            "Word": "happy",
            "PronAccuracy": 64,
            "PhoneInfos": [{
                "Phone": "e", "ReferencePhone": "æ", "PronAccuracy": 0.4,
                "Stress": True, "DetectedStress": False,
            }],
        }]
    }
    request = AsyncMock(side_effect=[first, detail])
    monkeypatch.setattr(pronunciation, "_request_evaluation", request)

    result = await pronunciation.evaluate_pronunciation(b"audio", "webm", "I am happy")

    assert result["status"] == "completed"
    assert result["overallScore"] == 82
    assert result["accuracyScore"] == 73
    assert result["issues"][0]["detectedIpa"] == "e"
    assert result["issues"][0]["referenceIpa"] == "æ"
    assert "重音" in result["issues"][0]["coaching"]
    assert request.await_args_list[0].args == (b"full", "I am happy", 1)
    assert request.await_args_list[1].args == (b"clip", "{::cmd{F_IPA=true}} happy", 4)
