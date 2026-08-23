"""Unit tests for followup chat — context assembly, streaming, retry."""

from unittest.mock import MagicMock, patch

import pytest

from services.followup_chat import (
    _build_followup_messages,
    _followup_context,
    followup_chat_stream,
)
from tests.unit.corrector_fakes import (
    ATTEMPT,
    SCENARIO,
    _empty_content_chunk,
    _fake_stream_client,
    _stream_chunk,
)


def test_followup_context_includes_scenario_and_feedback():
    ctx = _followup_context(SCENARIO, ATTEMPT)
    assert SCENARIO["mission"] in ctx
    assert ATTEMPT["transcript"] in ctx
    assert ATTEMPT["nativeVersion"] in ctx
    assert ATTEMPT["standardAnswer"] in ctx  # 标准答案也进追问上下文
    assert "remake it" in ctx          # gap better
    assert ATTEMPT["summary"] in ctx


def test_followup_context_empty_when_no_inputs():
    assert _followup_context(None, None) == ""


def test_build_followup_messages_maps_history_roles():
    history = [
        {"role": "user", "content": "为什么用 remake?"},
        {"role": "assistant", "content": "remake 指重新做一份"},
        {"role": "user", "content": ""},  # 空内容应被跳过
    ]
    messages = _build_followup_messages(SCENARIO, ATTEMPT, history, "还能怎么说？")
    # system + 2 条有效历史 + 当前问题 = 4
    assert len(messages) == 4
    assert messages[0].__class__.__name__ == "SystemMessage"
    assert messages[1].__class__.__name__ == "HumanMessage"
    assert messages[2].__class__.__name__ == "AIMessage"
    assert messages[-1].content == "还能怎么说？"


async def _collect_followup(question, scenario=SCENARIO, attempt=ATTEMPT, history=None):
    events = []
    async for event_type, data in followup_chat_stream(scenario, attempt, history, question):
        events.append((event_type, data))
    return events


@pytest.mark.asyncio
async def test_followup_empty_question_yields_error():
    events = await _collect_followup("   ")
    assert len(events) == 1
    assert events[0][0] == "error"


@pytest.mark.asyncio
async def test_followup_streams_chunks_then_done():
    chunks = [_stream_chunk("re"), _stream_chunk("make"), _empty_content_chunk()]
    fake = _fake_stream_client(chunks)
    with patch("services.followup_chat._get_client", return_value=fake):
        events = await _collect_followup("为什么用 remake?")
    chunk_texts = [d["text"] for t, d in events if t == "chunk"]
    done = [d for t, d in events if t == "done"]
    assert "".join(chunk_texts) == "remake"
    assert len(done) == 1
    assert done[0]["text"] == "remake"


@pytest.mark.asyncio
async def test_followup_exception_yields_error_event():
    fake = MagicMock()
    fake.astream = MagicMock(side_effect=Exception("connection refused"))
    with patch("services.followup_chat._get_client", return_value=fake):
        events = await _collect_followup("还能怎么说？")
    assert events[-1][0] == "error"
    assert events[-1][1]["message"]
    assert fake.astream.call_count == 2


@pytest.mark.asyncio
async def test_followup_retries_once_when_stream_fails_before_first_token():
    async def _success(*args, **kwargs):
        yield _stream_chunk("retry worked")

    fake = MagicMock()
    fake.astream = MagicMock(side_effect=[Exception("transient access denied"), _success()])
    with patch("services.followup_chat._get_client", return_value=fake):
        events = await _collect_followup("还能怎么说？")

    assert fake.astream.call_count == 2
    assert events == [
        ("chunk", {"text": "retry worked"}),
        ("done", {"text": "retry worked"}),
    ]


@pytest.mark.asyncio
async def test_followup_does_not_retry_after_partial_output():
    async def _partial_then_error(*args, **kwargs):
        yield _stream_chunk("partial")
        raise Exception("connection dropped")

    fake = MagicMock()
    fake.astream = MagicMock(return_value=_partial_then_error())
    with patch("services.followup_chat._get_client", return_value=fake):
        events = await _collect_followup("还能怎么说？")

    assert fake.astream.call_count == 1
    assert events[0] == ("chunk", {"text": "partial"})
    assert events[-1][0] == "error"
