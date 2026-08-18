from evals.graders.schema import better_in_native_version, required_fields, standard_answer_valid


def test_required_fields_include_standard_answer():
    passed, _ = required_fields({"summary": "s", "nativeVersion": "n", "gaps": []}, {})
    assert not passed  # 缺 standardAnswer
    passed, _ = required_fields(
        {"summary": "s", "nativeVersion": "n", "standardAnswer": "sa", "gaps": []}, {}
    )
    assert passed


def test_standard_answer_ok_when_english_and_nonempty():
    out = {"nativeVersion": "n", "standardAnswer": "Could I get a large coffee, please?"}
    passed, _ = standard_answer_valid(out, {})
    assert passed


def test_standard_answer_rejects_chinese():
    out = {"nativeVersion": "n", "standardAnswer": "我想要一杯大杯咖啡"}
    passed, reason = standard_answer_valid(out, {})
    assert not passed
    assert "Chinese" in reason


def test_standard_answer_rejects_empty_when_feedback_exists():
    out = {"nativeVersion": "Could you remake it?", "standardAnswer": ""}
    passed, _ = standard_answer_valid(out, {})
    assert not passed


def test_standard_answer_empty_ok_on_fast_path():
    out = {"nativeVersion": "", "standardAnswer": "", "gaps": []}
    passed, reason = standard_answer_valid(out, {})
    assert passed
    assert "fast-path" in reason


def test_better_in_native_ignores_sentence_initial_case():
    output = {
        "nativeVersion": "My flight is boarding soon, so could you remake it?",
        "gaps": [{"better": "my flight is boarding soon"}],
    }
    passed, _ = better_in_native_version(output, {})
    assert passed


def test_better_in_native_still_rejects_missing_phrase():
    output = {
        "nativeVersion": "Please send an ambulance.",
        "gaps": [{"better": "lost consciousness"}],
    }
    passed, reason = better_in_native_version(output, {})
    assert not passed
    assert "lost consciousness" in reason
