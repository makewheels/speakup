"""交互类型归一化与写入校验。

interactionType 区分场景题的两种交互：standard（旧题，可缺省）与
progressive_hints（渐进式按需提示）。读取侧缺失/未知一律归一为 standard，
旧题不会误入渐进交互；写入侧必须是合法值，拼写错误直接拒绝。
"""

STANDARD = "standard"
PROGRESSIVE_HINTS = "progressive_hints"

_VALID = {STANDARD, PROGRESSIVE_HINTS}


def normalize_interaction_type(value: object) -> str:
    """读取归一化：缺失/未知/非字符串都按 standard。"""
    return value if value in _VALID else STANDARD


def validate_new_interaction_type(value: object) -> str:
    """新题写入校验：非法值直接抛错，不能把拼写错误写进生产。"""
    if value in _VALID:
        return value
    raise ValueError(f"unknown interactionType: {value!r}")


def scenario_hints(scenario: dict | None) -> list[str]:
    """展示用有序提示列表；standard/缺失一律返回空数组。"""
    scenario = scenario or {}
    if normalize_interaction_type(scenario.get("interactionType")) != PROGRESSIVE_HINTS:
        return []
    return [h for h in scenario.get("hints") or [] if isinstance(h, str) and h.strip()]
