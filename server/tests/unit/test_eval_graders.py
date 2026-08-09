from evals.graders.schema import better_in_native_version


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
