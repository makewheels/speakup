"""Pure logic tests for the corrector — no Mongo, no real LLM."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.corrector import (
    CorrectResult,
    GapItem,
    ProgressInfo,
    _build_followup_messages,
    _build_messages,
    _followup_context,
    _parse_result,
    correct_text,
    correct_text_stream,
    followup_chat_stream,
)

SCENARIO = {
    "where": "☕️ 咖啡店 · 西雅图",
    "story": "你点的热拿铁被做成了冰美式。",
    "mission": "让店员重做，并表明你赶时间。",
}

PREV_ATTEMPT = {
    "transcript": "Please change it fast.",
    "gaps": [{"original": "change it fast", "better": "Could you remake it?"}],
}


def _fake_llm(result: CorrectResult):
    """Build a fake LangChain client. correct_text 现在走 raw ainvoke + JSON 解析路径，
    所以 fake client 直接返回带 .content 的 message 对象。"""
    fake_response = MagicMock()
    fake_response.content = result.model_dump_json()
    fake_response.response_metadata = {
        "model_name": "qwen3.7-plus-test",
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    fake_client = MagicMock()
    fake_client.ainvoke = AsyncMock(return_value=fake_response)
    return fake_client


def test_short_input_skips_llm_entirely():
    """Less than 3 words → fast path, no LLM call, no gaps."""
    result = asyncio.run(correct_text("hi"))
    assert result["gaps"] == []
    assert result["nativeVersion"] == ""
    assert result["summary"]  # has a "say more" hint


def test_empty_input_skips_llm():
    result = asyncio.run(correct_text(""))
    assert result["gaps"] == []


def test_valid_json_response_mapped_to_schema():
    gap = GapItem(original="cat sleeping", better="cat is sleeping", why="needs auxiliary 'is'", category="grammar", saveToReview=True)
    fake_result = CorrectResult(summary="Solid try, one slip.", nativeVersion="A cat is sleeping on the couch.", gaps=[gap])
    fake = _fake_llm(fake_result)
    with patch("services.corrector._get_client", return_value=fake):
        result = asyncio.run(correct_text("There is a cat sleeping on the couch", SCENARIO))
    assert result["summary"] == fake_result.summary
    assert result["nativeVersion"] == fake_result.nativeVersion
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["category"] == "grammar"
    assert result["gaps"][0]["saveToReview"] is True


def test_llm_exception_returns_error_message_not_crash():
    fake_client = MagicMock()
    fake_client.ainvoke = AsyncMock(side_effect=Exception("DashScope 400 BadRequest"))
    with patch("services.corrector._get_client", return_value=fake_client):
        result = asyncio.run(correct_text("There is a cat outside", SCENARIO))
    assert result["gaps"] == []
    assert "error" in result["summary"].lower()


# ── prompt 构造 ──────────────────────────────────────────────────────────────

def test_scenario_block_included_in_user_message():
    messages = _build_messages("I want a hot latte", scenario=SCENARIO)
    user = messages[-1].content
    assert SCENARIO["story"] in user
    assert SCENARIO["mission"] in user


def test_no_scenario_no_block():
    messages = _build_messages("I want a hot latte")
    assert "SCENARIO" not in messages[-1].content


def test_target_words_listed_for_custom_scenario():
    sc = {**SCENARIO, "targetWords": ["I'm in a rush", "Could you remake it"]}
    messages = _build_messages("hello there friend", scenario=sc)
    assert "I'm in a rush" in messages[-1].content


def test_scenario_points_listed_in_user_message():
    sc = {**SCENARIO, "points": ["请他重做成热拿铁", "说你赶时间"]}
    messages = _build_messages("hello there friend", scenario=sc)
    user = messages[-1].content
    assert "请他重做成热拿铁" in user
    assert "说你赶时间" in user


def test_retry_round_injects_progress_instructions():
    messages = _build_messages("Could you remake it? I'm in a rush", SCENARIO, PREV_ATTEMPT, round=2)
    system = messages[0].content
    assert "第 2 轮" in system
    assert PREV_ATTEMPT["transcript"] in system
    assert '"progress"' in system


def test_first_round_has_no_progress_instructions():
    messages = _build_messages("Could you remake it?", SCENARIO, None, round=1)
    assert "重说尝试" not in messages[0].content


# ── _parse_result（含 progress）────────────────────────────────────────────

def test_parse_result_with_progress():
    raw = """{"summary": "好多了", "nativeVersion": "x", "gaps": [],
              "progress": {"verdict": "passed", "fixed": ["Could you remake it?"], "remaining": [], "comment": "过关"}}"""
    result = _parse_result(raw)
    assert result["progress"]["verdict"] == "passed"
    assert result["progress"]["fixed"] == ["Could you remake it?"]


def test_parse_result_without_progress_is_none():
    raw = '{"summary": "ok", "nativeVersion": "x", "gaps": []}'
    assert _parse_result(raw)["progress"] is None


def test_parse_result_invalid_json_returns_failure_summary():
    result = _parse_result('{"summary": broken → arrows}')
    assert result["gaps"] == []
    assert "fail" in result["summary"].lower()


def test_progress_model_defaults():
    p = ProgressInfo()
    assert p.verdict == "improved"
    assert p.fixed == [] and p.remaining == []


# ── correct_text_stream 単元测试 ────────────────────────────────────────────

def _stream_chunk(text: str):
    chunk = MagicMock()
    chunk.content = text
    return chunk


def _empty_content_chunk():
    chunk = MagicMock()
    chunk.content = ""
    return chunk


def _fake_stream_client(chunks):
    async def _gen(*args, **kwargs):
        for c in chunks:
            yield c

    fake = MagicMock()
    fake.astream = MagicMock(return_value=_gen())
    return fake


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
    import json
    payload = {"summary": "nice", "nativeVersion": "A cat sleeps.", "gaps": []}
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
async def test_stream_done_carries_progress_on_retry():
    import json
    payload = {
        "summary": "好多了", "nativeVersion": "x", "gaps": [],
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
    import json
    payload = {"summary": "ok", "nativeVersion": "x", "gaps": []}
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


# ── 追问对话（followup chat）─────────────────────────────────────────────────

ATTEMPT = {
    "transcript": "Please change it fast.",
    "nativeVersion": "Could you remake this as a hot latte? I'm in a bit of a rush.",
    "summary": "任务基本完成，用词可更地道",
    "gaps": [
        {"category": "naturalness", "original": "change it fast", "better": "remake it", "why": "remake 更贴切"},
    ],
}


def test_followup_context_includes_scenario_and_feedback():
    ctx = _followup_context(SCENARIO, ATTEMPT)
    assert SCENARIO["mission"] in ctx
    assert ATTEMPT["transcript"] in ctx
    assert ATTEMPT["nativeVersion"] in ctx
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
    with patch("services.corrector._get_client", return_value=fake):
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
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect_followup("还能怎么说？")
    assert events[-1][0] == "error"
    assert events[-1][1]["message"]
