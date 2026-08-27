"""评分隔离：hints 文本与 hintCount 永不进入纠错 / 标准答案请求（AC-05）。

hints 只是 Session 快照里的展示字段；corrector 与标准答案的消息构造函数都走
字段白名单。这里直接对构造出的模型消息做断言：提示不在 prompt 里，且只有
hintCount 不同时，构造出的请求完全一致。
"""

import json

from services.corrector import _build_messages
from services.standard_answer import _question_snapshot, build_standard_answer_messages

SCENARIO_WITH_HINTS = {
    "kind": "task",
    "title": "外卖少送了一份菜",
    "where": "家里 · 晚餐时间",
    "story": "你点了两份主菜的外卖，骑手刚走你就发现少送了一份。",
    "mission": "找平台客服解决少送的菜",
    "points": ["说明订单里有一份菜没有送到", "要求补送或者退钱"],
    "interactionType": "progressive_hints",
    "hints": ["我点的两份菜只送到了一份。", "请帮我把缺的那份补送来。"],
    "difficulty": 2,
}


def _all_content(messages) -> str:
    return "\n".join(m.content for m in messages)


def test_hints_do_not_enter_corrector_messages():
    messages = _build_messages("Excuse me, one dish is missing.", SCENARIO_WITH_HINTS, None, 1, "scenario")
    text = _all_content(messages)
    for hint in SCENARIO_WITH_HINTS["hints"]:
        assert hint not in text
    assert "hints" not in text


def test_task_points_still_checked_but_only_points():
    text = _all_content(_build_messages("text", SCENARIO_WITH_HINTS, None, 1, "scenario"))
    for point in SCENARIO_WITH_HINTS["points"]:
        assert point in text


def test_only_hint_count_differs_model_request_identical():
    """hintCount 只存在 Session/Attempt 上；相同题目相同作答、仅提示计数不同的两个会话，构造出的模型请求完全一致。"""
    a = dict(SCENARIO_WITH_HINTS)
    b = dict(SCENARIO_WITH_HINTS)
    text = "I ordered two dishes but only got one."
    assert _build_messages(text, a, None, 1, "scenario") == _build_messages(text, b, None, 1, "scenario")


def test_progressive_non_task_has_no_required_points_block():
    scenario = {**SCENARIO_WITH_HINTS, "kind": "chat", "points": []}
    text = _all_content(_build_messages("hello", scenario, None, 1, "scenario"))
    assert "应说到的内容" not in text


def test_standard_answer_snapshot_excludes_hints():
    snapshot = _question_snapshot(SCENARIO_WITH_HINTS)
    assert "hints" not in snapshot
    serialized = json.dumps(snapshot, ensure_ascii=False)
    for hint in SCENARIO_WITH_HINTS["hints"]:
        assert hint not in serialized
    assert snapshot.get("points") == SCENARIO_WITH_HINTS["points"]


def test_standard_answer_messages_identical_with_or_without_hints():
    with_hints = dict(SCENARIO_WITH_HINTS)
    without = {k: v for k, v in SCENARIO_WITH_HINTS.items() if k not in ("hints", "interactionType")}
    assert (
        build_standard_answer_messages(with_hints)[1].content
        == build_standard_answer_messages(without)[1].content
    )
