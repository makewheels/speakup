"""自由说模式的 corrector 逻辑：prompt 选择、话题上下文、task 类别归一。无 Mongo、无 LLM。"""

from services.corrector import (
    FREE_SYSTEM_PROMPT,
    _build_messages,
    _coerce_result,
    _parse_result,
    mode_of_scenario,
)

FREE_SNAPSHOT = {"kind": "free", "title": "Your favorite season", "freeTopic": "Your favorite season"}
FREE_NO_TOPIC = {"kind": "free", "title": "自由说", "freeTopic": ""}


def test_mode_of_scenario_detects_free_snapshot():
    assert mode_of_scenario(FREE_SNAPSHOT) == "free"
    assert mode_of_scenario({"kind": "task"}) == "scenario"
    assert mode_of_scenario({}) == "scenario"
    assert mode_of_scenario(None) == "scenario"


def test_free_mode_uses_free_prompt_without_task_judgement():
    messages = _build_messages("I go to park yesterday", FREE_SNAPSHOT, None, 1, "free")
    system = messages[0].content
    assert system == FREE_SYSTEM_PROMPT or system.startswith("你是英语口语教练。学习者在")
    assert "自由说" in system
    assert "不判断任务完成度" in system
    assert "绝不要用 task" in system


def test_free_mode_user_message_carries_topic_not_scenario_block():
    messages = _build_messages("I go to park yesterday", FREE_SNAPSHOT, None, 1, "free")
    user = messages[-1].content
    assert "Your favorite season" in user
    assert "SCENARIO" not in user
    assert "任务" not in user.split("学习者刚说的话")[0].replace("不判完成度", "")


def test_free_mode_no_topic_has_no_topic_line():
    messages = _build_messages("hello there my friend", FREE_NO_TOPIC, None, 1, "free")
    assert "话题" not in messages[-1].content


def test_free_snapshot_never_renders_scenario_block():
    """kind=free 的快照走场景块也要返回空（追问上下文等共用路径）。"""
    messages = _build_messages("I like it a lot", FREE_SNAPSHOT, None, 1, "scenario")
    assert "SCENARIO" not in messages[-1].content


def test_free_retry_prompt_has_no_task_wording():
    prev = {"transcript": "I go park", "gaps": [{"original": "I go park", "better": "I went to the park"}]}
    messages = _build_messages("I went to the park yesterday", FREE_SNAPSHOT, prev, 2, "free")
    system = messages[0].content
    assert "第 2 轮" in system
    assert "同一个话题的重说尝试" in system
    assert "任务确实办成" not in system


def test_scenario_retry_prompt_unchanged():
    prev = {"transcript": "please change it", "gaps": []}
    sc = {"kind": "task", "where": "咖啡店", "story": "s", "mission": "m"}
    messages = _build_messages("please change it now", sc, prev, 2, "scenario")
    assert "任务确实办成" in messages[0].content


def test_coerce_result_maps_task_to_naturalness_in_free_mode():
    data = {
        "summary": "s",
        "nativeVersion": "n",
        "gaps": [{"original": "a", "better": "b", "why": "w", "category": "task"}],
    }
    assert _coerce_result(data, free=True)["gaps"][0]["category"] == "naturalness"
    assert _coerce_result(data)["gaps"][0]["category"] == "task"


def test_parse_result_free_mode_maps_task_category():
    raw = ('{"summary": "ok", "nativeVersion": "n", "gaps": ['
           '{"original": "a", "better": "b", "why": "w", "category": "task"}]}')
    result = _parse_result(raw, free=True)
    assert result["gaps"][0]["category"] == "naturalness"


def test_parse_result_free_mode_allows_empty_standard_answer():
    raw = '{"summary": "ok", "nativeVersion": "n", "standardAnswer": "", "gaps": []}'
    result = _parse_result(raw, free=True)
    assert result["standardAnswer"] == ""
