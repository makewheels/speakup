"""Pure logic tests for the corrector — no Mongo, no real LLM."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.corrector import (
    CorrectResult,
    GapItem,
    ProgressInfo,
    _build_messages,
    _get_client,
    _is_too_short,
    _parse_result,
    correct_text,
    correct_text_stream,
)
from services.followup_chat import _build_followup_messages, _followup_context, followup_chat_stream

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


def test_get_client_disables_thinking_for_dashscope(monkeypatch):
    fake_chat = MagicMock(return_value="client")
    monkeypatch.setattr("services.corrector._client", None)
    monkeypatch.setattr("services.corrector.CHAT_THINKING", False)
    monkeypatch.setattr(
        "services.corrector.CHAT_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setattr("services.corrector.ChatOpenAI", fake_chat)

    assert _get_client() == "client"

    assert fake_chat.call_args.kwargs["extra_body"] == {"enable_thinking": False}


def test_get_client_uses_volcengine_thinking_shape(monkeypatch):
    fake_chat = MagicMock(return_value="client")
    monkeypatch.setattr("services.corrector._client", None)
    monkeypatch.setattr("services.corrector.CHAT_THINKING", False)
    monkeypatch.setattr("services.corrector.CHAT_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    monkeypatch.setattr("services.corrector.ChatOpenAI", fake_chat)

    assert _get_client() == "client"
    assert fake_chat.call_args.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_get_client_uses_deepseek_thinking_shape(monkeypatch):
    """DeepSeek 官方 API 不认 enable_thinking，必须用 thinking.type，
    否则思考模型先吐几千字 reasoning，用户端干等几十秒。"""
    fake_chat = MagicMock(return_value="client")
    monkeypatch.setattr("services.corrector._client", None)
    monkeypatch.setattr("services.corrector.CHAT_THINKING", False)
    monkeypatch.setattr("services.corrector.CHAT_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setattr("services.corrector.ChatOpenAI", fake_chat)

    assert _get_client() == "client"
    assert fake_chat.call_args.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert fake_chat.call_args.kwargs["stream_usage"] is True


def test_short_input_skips_llm_entirely():
    """Less than 3 words → fast path, no LLM call, no gaps."""
    result = asyncio.run(correct_text("hi"))
    assert result["gaps"] == []
    assert result["nativeVersion"] == ""
    assert result["standardAnswer"] == ""
    assert result["summary"]  # has a "say more" hint


def test_empty_input_skips_llm():
    result = asyncio.run(correct_text(""))
    assert result["gaps"] == []


def test_chinese_only_input_must_reach_evaluator_instead_of_short_fast_path():
    assert _is_too_short("这个我不知道怎么说") is False
    assert _is_too_short("I 不知道") is False
    assert _is_too_short("hi") is True


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


def test_system_prompt_marks_non_english_answer_as_failed_task():
    messages = _build_messages("我想让他重做拿铁", scenario=SCENARIO)
    system = messages[0].content
    assert "主要是中文" in system
    assert "score 不得高于 2.0" in system
    assert "忽略大小写" in system
    assert "所有必要信息" in system


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


def test_system_prompt_requires_standard_answer_independent_of_learner():
    """标准答案板块：prompt 必须要求输出 standardAnswer，且明确它脱离学习者原话。"""
    messages = _build_messages("I want a hot latte", scenario=SCENARIO)
    system = messages[0].content
    assert '"standardAnswer"' in system
    assert "完全脱离学习者原话" in system
    assert "nativeVersion" in system  # 两者分工都写进 prompt


def test_system_prompt_requires_chinese_hint_per_gap():
    """复习卡正面用中文提示词主动回忆：prompt 必须要求每个 gap 带 better 的中文意思。"""
    messages = _build_messages("I want a hot latte", scenario=SCENARIO)
    system = messages[0].content
    assert '"chinese"' in system
    assert "提示词" in system


def test_parse_result_maps_gap_chinese():
    raw = """{"summary": "ok", "nativeVersion": "Could you remake it?", "gaps": [
        {"original": "redo", "better": "remake", "chinese": "重做一下", "why": "x", "category": "vocabulary"}
    ]}"""
    result = _parse_result(raw)
    assert result["gaps"][0]["chinese"] == "重做一下"


def test_parse_result_gap_chinese_defaults_empty():
    raw = """{"summary": "ok", "nativeVersion": "x", "gaps": [
        {"original": "a", "better": "b", "why": "x", "category": "vocabulary"}
    ]}"""
    assert _parse_result(raw)["gaps"][0]["chinese"] == ""


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


def test_parse_result_maps_standard_answer():
    raw = ('{"summary": "ok", "nativeVersion": "Could you remake it?", '
           '"standardAnswer": "Excuse me, could you remake my latte? I\'m in a rush.", "gaps": []}')
    result = _parse_result(raw)
    assert result["standardAnswer"] == "Excuse me, could you remake my latte? I'm in a rush."


def test_parse_result_accepts_snake_case_standard_answer():
    raw = ('{"summary": "ok", "nativeVersion": "x", "standard_answer": "Could I get a large coffee?", '
           '"gaps": []}')
    assert _parse_result(raw)["standardAnswer"] == "Could I get a large coffee?"


def test_parse_result_standard_answer_defaults_empty():
    raw = '{"summary": "ok", "nativeVersion": "x", "gaps": []}'
    assert _parse_result(raw)["standardAnswer"] == ""


def test_parse_result_invalid_json_returns_failure_summary():
    result = _parse_result('{"summary": broken → arrows}')
    assert result["gaps"] == []
    assert "could not be parsed" in result["summary"].lower()


def test_parse_result_keeps_feedback_when_model_output_is_wrapped_or_noisy():
    raw = """
    Sure, here is the JSON:
    ```json
    {
      "summary": "请求可以更自然",
      "native_version": "Could you remake my latte? I'm in a hurry.",
      "score": "6.5/9",
      "gaps": [
        {
          "original": "redo my latte",
          "better": "remake my latte",
          "why": "redo 偏随意，remake 更贴合重做饮品。",
          "category": "phrasing",
          "saveToReview": true
        }
      ],
      "progress": {"verdict": "needs-work", "fixed": [], "remaining": ["remake my latte"], "comment": "还要更自然"}
    }
    ```
    """
    result = _parse_result(raw)

    assert result["summary"] == "请求可以更自然"
    assert result["nativeVersion"] == "Could you remake my latte? I'm in a hurry."
    assert result["score"] == 6.5
    assert result["gaps"][0]["better"] == "remake my latte"
    assert result["gaps"][0]["category"] == "vocabulary"
    assert result["progress"]["verdict"] == "improved"


def test_parse_result_accepts_content_blocks_and_trailing_commas():
    raw = [
        {
            "type": "text",
            "text": """
            {
              "summary": "任务完成了",
              "nativeVersion": "Could you remake my latte?",
              "score": "6.5",
              "gaps": [
                {"original": "redo", "better": "remake", "why": "remake 更准确", "category": "vocabulary",},
              ],
            }
            """,
        }
    ]
    result = _parse_result(raw)

    assert result["nativeVersion"] == "Could you remake my latte?"
    assert result["score"] == 6.5
    assert result["gaps"][0]["better"] == "remake"


def test_progress_model_defaults():
    p = ProgressInfo()
    assert p.verdict == "improved"
    assert p.fixed == [] and p.remaining == []


# ── correct_text_stream 単元测试 ────────────────────────────────────────────

def _stream_chunk(text: str, response_metadata: dict | None = None):
    chunk = MagicMock()
    chunk.content = text
    chunk.response_metadata = response_metadata or {}
    chunk.usage_metadata = None  # 真实 chunk 无 usage 时就是 None，避免 MagicMock 误判
    return chunk


def _empty_content_chunk():
    chunk = MagicMock()
    chunk.content = ""
    chunk.usage_metadata = None
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
async def test_stream_emits_usage_event_before_done():
    """stream_usage=True 时，finish_reason chunk 带顶层 usage_metadata（input_tokens/output_tokens）
    → 在 done 之前 yield usage 事件，供前端展示本次 token 消耗。"""
    import json
    payload = {"summary": "nice", "nativeVersion": "A cat sleeps.", "gaps": []}
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
    import json
    payload = {"summary": "ok", "nativeVersion": "x", "gaps": []}
    fake = _fake_stream_client([_stream_chunk(json.dumps(payload))])
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here")
    assert [t for t, _ in events] == ["chunk", "done"]


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
    "standardAnswer": "Excuse me, I ordered a hot latte. Could you remake it? I'm in a rush.",
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
