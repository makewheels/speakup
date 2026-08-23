"""独立标准答案的上下文隔离与解析。"""

import json

import pytest

from services import standard_answer
from services.llm_audit import serialize_messages


SCENARIO = {
    "kind": "task",
    "title": "咖啡做错了",
    "where": "咖啡店",
    "story": "热拿铁被做成冰饮。",
    "mission": "请店员重做，并说明你赶时间。",
    "points": ["说明饮品做错", "礼貌请求重做"],
    "targetWords": ["PRIVATE_TARGET_WORD"],
    "transcript": "PRIVATE_CURRENT_ANSWER",
    "nativeVersion": "PRIVATE_CORRECTION",
    "gaps": [{"better": "PRIVATE_GAP"}],
    "attempts": [{"transcript": "PRIVATE_PREVIOUS_ANSWER"}],
}


def _serialized_text(messages: list) -> str:
    return json.dumps(serialize_messages(messages), ensure_ascii=False)


def test_standard_answer_messages_only_contain_allowlisted_question_fields():
    text = _serialized_text(standard_answer.build_standard_answer_messages(SCENARIO))

    for allowed in (SCENARIO["title"], SCENARIO["where"], SCENARIO["story"], SCENARIO["mission"], *SCENARIO["points"]):
        assert allowed in text
    for forbidden in (
        "PRIVATE_TARGET_WORD",
        "PRIVATE_CURRENT_ANSWER",
        "PRIVATE_CORRECTION",
        "PRIVATE_GAP",
        "PRIVATE_PREVIOUS_ANSWER",
        "targetWords",
        "transcript",
        "nativeVersion",
        "gaps",
        "attempts",
    ):
        assert forbidden not in text


def test_free_standard_answer_messages_only_contain_topic():
    scenario = {
        "kind": "free",
        "freeTopic": "Describe your ideal weekend",
        "title": "PRIVATE_TITLE",
        "transcript": "PRIVATE_ANSWER",
    }
    text = _serialized_text(standard_answer.build_standard_answer_messages(scenario))
    assert "Describe your ideal weekend" in text
    assert "PRIVATE_TITLE" not in text
    assert "PRIVATE_ANSWER" not in text


def test_parse_standard_answer_accepts_wrapped_json_and_snake_case():
    raw = 'result: ```json\n{"result":{"standard_answer":"Could I get a hot latte, please?"}}\n```'
    assert standard_answer.parse_standard_answer(raw) == {
        "standardAnswer": "Could I get a hot latte, please?"
    }


@pytest.mark.asyncio
async def test_invalid_standard_answer_makes_one_clean_request_then_degrades(monkeypatch):
    calls = []

    async def fake_invoke(client, messages, *, kind, link_to, parser):
        calls.append((kind, messages))
        return {"parsed": {"standardAnswer": ""}, "error": None}

    monkeypatch.setattr(standard_answer, "audited_invoke", fake_invoke)
    answer = await standard_answer.generate_standard_answer(
        SCENARIO,
        object(),
        link_to={
            "round": 2,
            "transcript": "PRIVATE_LINKED_ANSWER",
            "nativeVersion": "PRIVATE_LINKED_CORRECTION",
        },
    )

    assert answer == ""
    assert [kind for kind, _ in calls] == ["standard_answer"]
    for _, messages in calls:
        text = _serialized_text(messages)
        assert "PRIVATE_CURRENT_ANSWER" not in text
        assert "PRIVATE_PREVIOUS_ANSWER" not in text
        assert "PRIVATE_GAP" not in text
        assert "PRIVATE_CORRECTION" not in text
        assert "PRIVATE_LINKED_ANSWER" not in text
        assert "PRIVATE_LINKED_CORRECTION" not in text
