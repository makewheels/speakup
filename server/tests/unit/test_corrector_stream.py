"""correct_text_stream unit tests — chunk merging, isolated standard answer, usage events."""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.corrector import correct_text_stream
from tests.unit.corrector_fakes import (
    PREV_ATTEMPT,
    SCENARIO,
    _DualRequestClient,
    _empty_content_chunk,
    _fake_stream_client,
    _stream_chunk,
)


async def _collect(text, scenario=None, prev=None, round=1):
    events = []
    async for event_type, data in correct_text_stream(text, scenario, prev, round):
        events.append((event_type, data))
    return events



@pytest.mark.asyncio
async def test_stream_short_input_yields_done_immediately():
    events = await _collect("hi")
    assert len(events) == 1
    assert events[0][0] == "done"
    assert events[0][1]["gaps"] == []


@pytest.mark.asyncio
async def test_stream_emits_chunk_events_then_done():
    payload = {"summary": "nice", "score": 6.0, "gaps": []}
    raw = json.dumps(payload)
    chunks = [_stream_chunk(c) for c in raw]
    fake = _fake_stream_client(chunks)
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat on the sofa", SCENARIO)
    chunk_texts = [d["text"] for t, d in events if t == "chunk"]
    done_events = [d for t, d in events if t == "done"]
    assert "".join(chunk_texts) == raw
    assert len(done_events) == 1
    assert done_events[0]["summary"] == "nice"


@pytest.mark.asyncio
async def test_stream_runs_standard_request_in_parallel_and_merges_done():
    correction = {"summary": "已纠正", "score": 6.0, "gaps": []}
    client = _DualRequestClient(correction, "Excuse me, could you remake my latte?")
    with patch("services.corrector._get_client", return_value=client):
        events = await _collect("Please change my latte now", SCENARIO)

    done = [data for event, data in events if event == "done"][0]
    assert client.stream_calls == 1
    assert client.correction_calls == 0
    assert client.standard_calls == 1
    assert done["standardAnswer"] == "Excuse me, could you remake my latte?"


@pytest.mark.asyncio
async def test_stream_correction_fallback_does_not_repeat_standard_request():
    correction = {"summary": "已纠正", "score": 6.0, "gaps": []}
    client = _DualRequestClient(
        correction,
        "Excuse me, could you remake my latte?",
        modes={"broken_stream"},
    )
    with patch("services.corrector._get_client", return_value=client):
        events = await _collect("Please change my latte now", SCENARIO)

    done = [data for event, data in events if event == "done"][0]
    assert client.stream_calls == 1
    assert client.correction_calls == 1
    assert client.standard_calls == 1
    assert done["score"] == 6.0
    assert done["standardAnswer"] == "Excuse me, could you remake my latte?"


@pytest.mark.asyncio
async def test_stream_standard_failure_degrades_without_losing_correction():
    correction = {"summary": "已纠正", "score": 6.0, "gaps": []}
    client = _DualRequestClient(correction, "", modes={"fail_standard"})
    with patch("services.corrector._get_client", return_value=client):
        events = await _collect("Please change my latte now", SCENARIO)

    done = [data for event, data in events if event == "done"][0]
    assert not [data for event, data in events if event == "error"]
    assert client.stream_calls == 1
    assert client.standard_calls == 1
    assert done["score"] == 6.0
    assert done["standardAnswer"] == ""


@pytest.mark.asyncio
async def test_stream_correction_and_fallback_failure_keep_standard_answer():
    correction = {"summary": "", "gaps": []}
    client = _DualRequestClient(
        correction,
        "Excuse me, could you remake my latte?",
        modes={"fail_correction", "fail_stream"},
    )
    with patch("services.corrector._get_client", return_value=client):
        events = await _collect("Please change my latte now", SCENARIO)

    done = [data for event, data in events if event == "done"][0]
    assert not [data for event, data in events if event == "error"]
    assert client.stream_calls == 1
    assert client.correction_calls == 1  # 仅纠正分支允许一次 fallback
    assert client.standard_calls == 1
    assert "nativeVersion" not in done
    assert done["standardAnswer"] == "Excuse me, could you remake my latte?"


@pytest.mark.asyncio
async def test_stream_emits_usage_event_before_done():
    """stream_usage=True 时，finish_reason chunk 带顶层 usage_metadata（input_tokens/output_tokens）
    → 在 done 之前 yield usage 事件，供前端展示本次 token 消耗。"""
    payload = {"summary": "nice", "score": 6.0, "gaps": []}
    # 实测 langchain-openai 1.2.2 + DeepSeek 的 finish chunk 形态
    finish = _stream_chunk("", {"model_name": "deepseek-v4-flash", "finish_reason": "stop"})
    finish.usage_metadata = {"input_tokens": 321, "output_tokens": 65, "total_tokens": 386}
    chunks = [_stream_chunk(json.dumps(payload)), finish]
    fake = _fake_stream_client(chunks)
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat on the sofa", SCENARIO)
    types = [t for t, _ in events]
    assert types == ["chunk", "usage", "done"]
    usage = [d for t, d in events if t == "usage"][0]
    assert usage == {"model": "deepseek-v4-flash", "promptTokens": 321, "completionTokens": 65}


@pytest.mark.asyncio
async def test_stream_no_usage_event_when_metadata_missing():
    """末尾 chunk 不带 usage（上游没开 include_usage）→ 不 yield usage 事件，行为向后兼容。"""
    payload = {"summary": "ok", "score": 6.0, "gaps": []}
    fake = _fake_stream_client([_stream_chunk(json.dumps(payload))])
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here")
    assert [t for t, _ in events] == ["chunk", "done"]


@pytest.mark.asyncio
async def test_stream_done_carries_progress_on_retry():
    payload = {
        "summary": "好多了", "score": 6.5, "gaps": [],
        "progress": {"verdict": "improved", "fixed": ["a"], "remaining": ["b"], "comment": "ok"},
    }
    fake = _fake_stream_client([_stream_chunk(json.dumps(payload))])
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("Could you remake it please now", SCENARIO, PREV_ATTEMPT, round=2)
    done = [d for t, d in events if t == "done"][0]
    assert done["progress"]["verdict"] == "improved"


@pytest.mark.asyncio
async def test_stream_skips_empty_content_chunk():
    """Chunks with empty content must not generate chunk events."""
    payload = {"summary": "ok", "score": 6.0, "gaps": []}
    raw = json.dumps(payload)
    chunks = [_stream_chunk(raw), _empty_content_chunk()]
    fake = _fake_stream_client(chunks)
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here")
    assert sum(1 for t, _ in events if t == "done") == 1
    assert sum(1 for t, _ in events if t == "error") == 0


@pytest.mark.asyncio
async def test_stream_exception_yields_error_event_not_crash():
    """Any exception in the stream → error event, not unhandled exception."""
    fake = MagicMock()
    fake.astream = MagicMock(side_effect=Exception("connection refused"))
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here")
    assert len(events) == 1
    assert events[0][0] == "error"
    assert "error" in events[0][1]["message"].lower()
