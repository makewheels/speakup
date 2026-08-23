"""Pure logic tests for the corrector — no Mongo, no real LLM."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.corrector import (
    CorrectResult,
    GapItem,
    ProgressInfo,
    _build_messages,
    _get_client,
    _is_too_short,
    _parse_result,
    correct_text,
)
from tests.unit.corrector_fakes import (
    PREV_ATTEMPT,
    SCENARIO,
    _DualRequestClient,
    _fake_llm,
)


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


def test_correct_text_makes_two_isolated_requests_and_merges_results():
    correction = {
        "summary": "纠正完成",
        "nativeVersion": "Could you remake it?",
        "standardAnswer": "must be ignored",
        "gaps": [],
    }
    client = _DualRequestClient(correction, "Excuse me, could you remake my latte?")
    with patch("services.corrector._get_client", return_value=client):
        result = asyncio.run(correct_text("Please change my latte now", SCENARIO))

    assert client.correction_calls == 1
    assert client.standard_calls == 1
    assert result["nativeVersion"] == "Could you remake it?"
    assert result["standardAnswer"] == "Excuse me, could you remake my latte?"


def test_correct_text_standard_failure_keeps_non_stream_correction():
    correction = {"summary": "纠正完成", "nativeVersion": "Could you remake it?", "gaps": []}
    client = _DualRequestClient(correction, "", modes={"fail_standard"})
    with patch("services.corrector._get_client", return_value=client):
        result = asyncio.run(correct_text("Please change my latte now", SCENARIO))

    assert client.correction_calls == 1
    assert client.standard_calls == 1
    assert result["nativeVersion"] == "Could you remake it?"
    assert result["standardAnswer"] == ""


def test_correct_text_correction_failure_keeps_non_stream_standard_answer():
    correction = {"summary": "", "nativeVersion": "", "gaps": []}
    client = _DualRequestClient(
        correction,
        "Excuse me, could you remake my latte?",
        modes={"fail_correction"},
    )
    with patch("services.corrector._get_client", return_value=client):
        result = asyncio.run(correct_text("Please change my latte now", SCENARIO))

    assert client.correction_calls == 1
    assert client.standard_calls == 1
    assert result["nativeVersion"] == ""
    assert result["standardAnswer"] == "Excuse me, could you remake my latte?"


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


def test_correction_prompt_does_not_generate_standard_answer_or_note():
    """纠正请求只负责纠正；标准答案和笔记不能再出现在它的输出 schema。"""
    messages = _build_messages("I want a hot latte", scenario=SCENARIO)
    system = messages[0].content
    assert "standardAnswer" not in system
    assert "note" not in system
    assert "noteChinese" not in system
    assert '"nativeVersion"' in system


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


def test_parse_result_maps_example_chinese():
    raw = """{"summary": "ok", "nativeVersion": "Could you remake it?", "gaps": [
        {"original": "redo", "better": "remake", "example": "Could you remake it?",
         "exampleChinese": "你能重做一下吗？", "why": "更自然", "category": "vocabulary"}
    ]}"""
    assert _parse_result(raw)["gaps"][0]["exampleChinese"] == "你能重做一下吗？"



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


def test_parse_result_ignores_standard_answer_and_auto_note_from_correction_model():
    raw = ('{"summary": "ok", "nativeVersion": "Could you remake it?", '
           '"standardAnswer": "copied learner answer", "note": "auto note", '
           '"noteChinese": "自动笔记", "gaps": []}')
    result = _parse_result(raw)
    assert result["standardAnswer"] == ""
    assert result["note"] == ""
    assert result["noteChinese"] == ""


def test_parse_result_ignores_snake_case_standard_answer_too():
    raw = ('{"summary": "ok", "nativeVersion": "x", "standard_answer": "Could I get a large coffee?", '
           '"gaps": []}')
    assert _parse_result(raw)["standardAnswer"] == ""


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
