import pytest

from services.interaction_types import (
    PROGRESSIVE_HINTS,
    STANDARD,
    normalize_interaction_type,
    scenario_hints,
    validate_new_interaction_type,
)


def test_missing_and_unknown_normalize_to_standard():
    """旧题缺字段或出现未知值时一律按 standard，绝不触发渐进交互。"""
    assert normalize_interaction_type(None) == STANDARD
    assert normalize_interaction_type("") == STANDARD
    assert normalize_interaction_type("progressive") == STANDARD
    assert normalize_interaction_type("PROGRESSIVE_HINTS") == STANDARD
    assert normalize_interaction_type(123) == STANDARD


def test_known_values_pass_through():
    assert normalize_interaction_type(STANDARD) == STANDARD
    assert normalize_interaction_type(PROGRESSIVE_HINTS) == PROGRESSIVE_HINTS


def test_validate_new_rejects_unknown():
    """新写入必须是合法值，拼写错误不能进生产。"""
    assert validate_new_interaction_type(STANDARD) == STANDARD
    assert validate_new_interaction_type(PROGRESSIVE_HINTS) == PROGRESSIVE_HINTS
    with pytest.raises(ValueError):
        validate_new_interaction_type("progressive-hints")
    with pytest.raises(ValueError):
        validate_new_interaction_type(None)


def test_scenario_hints_only_for_progressive():
    progressive = {"interactionType": PROGRESSIVE_HINTS, "hints": ["甲", "", "  ", "乙", 3]}
    assert scenario_hints(progressive) == ["甲", "乙"]
    assert scenario_hints({"hints": ["甲"]}) == []
    assert scenario_hints(None) == []
    assert scenario_hints({"interactionType": "weird", "hints": ["甲"]}) == []
