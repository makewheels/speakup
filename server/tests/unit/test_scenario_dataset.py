from __future__ import annotations

from copy import deepcopy

from evals.scenario_dataset import (
    load_families,
    summarize,
    validate_pilot_dataset,
)
from evals.scenario_review import render_review_html


def test_pilot_dataset_is_balanced_and_valid():
    families = load_families()
    assert validate_pilot_dataset(families) == []

    summary = summarize(families)
    assert summary.families == 8
    assert summary.cases == 24
    assert summary.buckets == {"positive": 8, "negative": 8, "boundary": 8}
    assert len(summary.domains) == 8
    assert summary.kinds == {"task": 15, "explain": 3, "chat": 3, "opinion": 3}


def test_dataset_contains_semantic_failures_that_clear_hard_rules():
    families = load_families()
    cases = [case for family in families for case in family["cases"]]
    semantic_only = [
        case
        for case in cases
        if "semantic_only_failure" in case["annotation"]["failureTags"]
    ]
    assert len(semantic_only) >= 3
    assert all(case["annotation"]["expectedHardFailures"] == [] for case in semantic_only)


def test_validator_catches_a_stale_hard_failure_label():
    families = deepcopy(load_families())
    families[0]["cases"][0]["annotation"]["expectedHardFailures"] = ["story_length"]
    errors = validate_pilot_dataset(families)
    assert any("hard failures mismatch" in error for error in errors)


def test_review_page_contains_triplets_and_filters():
    page = render_review_html(load_families())
    assert "SpeakUp 题目评测集 · Pilot v1" in page
    assert "travel-train-rebooking-positive" not in page  # 页面展示内容，不暴露内部 case id
    assert "错过末班前的转车" in page
    assert 'id="bucket"' in page
    assert page.count('class="case"') == 24
