from evals.graders.schema import (
    gap_original_grounded,
    required_fields,
    standard_answer_valid,
)


def test_required_fields_include_standard_answer():
    passed, _ = required_fields({"summary": "s", "gaps": []}, {})
    assert not passed  # 缺 standardAnswer
    passed, _ = required_fields(
        {"summary": "s", "standardAnswer": "sa", "gaps": []}, {}
    )
    assert passed


def test_standard_answer_ok_when_english_and_nonempty():
    out = {"score": 6.0, "standardAnswer": "Could I get a large coffee, please?"}
    passed, _ = standard_answer_valid(out, {})
    assert passed


def test_standard_answer_rejects_chinese():
    out = {"score": 6.0, "standardAnswer": "我想要一杯大杯咖啡"}
    passed, reason = standard_answer_valid(out, {})
    assert not passed
    assert "Chinese" in reason


def test_standard_answer_rejects_empty_when_feedback_exists():
    out = {"score": 6.0, "standardAnswer": ""}
    passed, _ = standard_answer_valid(out, {})
    assert not passed


def test_standard_answer_empty_ok_on_fast_path():
    out = {"score": None, "standardAnswer": "", "gaps": []}
    passed, reason = standard_answer_valid(out, {})
    assert passed
    assert "fast-path" in reason


def test_gap_original_can_be_a_full_grounded_sentence():
    output = {
        "gaps": [{"category": "grammar", "original": "I am hurry.", "better": "I am in a hurry."}],
    }
    passed, _ = gap_original_grounded(output, {"text": "I am hurry. Please remake it."})
    assert passed


def test_gap_original_rejects_model_invented_source_text():
    output = {
        "gaps": [{"category": "grammar", "original": "I was late.", "better": "I am late."}],
    }
    passed, reason = gap_original_grounded(output, {"text": "I am hurry."})
    assert not passed
    assert "I was late" in reason
