"""evals.compare 的纯逻辑测试：spec 解析 + 报告渲染。不调 LLM。"""
import pytest

from evals.compare import ModelSpec, parse_specs, render_summary, render_html, to_jsonable
from evals.harness import Task, TaskReport, TrialResult


def test_parse_specs_defaults():
    specs = parse_specs("glm-5.2,qwen3-max", "https://example.com/v1", "MY_KEY")
    assert specs == [
        ModelSpec(model="glm-5.2", base_url="https://example.com/v1", key_env="MY_KEY"),
        ModelSpec(model="qwen3-max", base_url="https://example.com/v1", key_env="MY_KEY"),
    ]


def test_parse_specs_full_override():
    specs = parse_specs(
        "deepseek-chat@https://api.deepseek.com/v1@DEEPSEEK_API_KEY",
        "https://example.com/v1", "MY_KEY",
    )
    assert specs[0].base_url == "https://api.deepseek.com/v1"
    assert specs[0].key_env == "DEEPSEEK_API_KEY"


def test_parse_specs_rejects_empty_and_malformed():
    with pytest.raises(SystemExit):
        parse_specs(" , ", "https://example.com/v1", "MY_KEY")
    with pytest.raises(SystemExit):
        parse_specs("a@b@c@d", "https://example.com/v1", "MY_KEY")


def _fake_report(task_id: str, passed: bool, score: float = 7.0) -> TaskReport:
    task = Task(id=task_id, desc=f"desc of {task_id}", input={"text": "hi"}, expectations=[])
    grader = {"grader": "schema:json", "passed": passed, "reason": "ok" if passed else "bad"}
    trial = TrialResult(
        trial_index=0, duration_ms=1234,
        llm_output={"score": score, "gaps": [], "summary": "s", "nativeVersion": "n"},
        grader_results=[grader],
    )
    return TaskReport(task=task, trials=[trial])


def test_summary_and_html_render():
    results = {
        "model-a": [_fake_report("t1", True), _fake_report("t2", False)],
        "model-b": [_fake_report("t1", True), _fake_report("t2", True)],
    }
    summary = render_summary(results, k=1)
    assert "model-a" in summary and "model-b" in summary
    assert "1/2" in summary  # model-a pass^k

    page = render_html(results, k=1, meta="test meta")
    assert "model-a" in page and "t1" in page and "test meta" in page
    assert "matrix" in page

    data = to_jsonable(results)
    assert data["model-a"][1]["pass_pow_k"] == 0.0
    assert data["model-b"][1]["trials"][0]["llm_output"]["score"] == 7.0
