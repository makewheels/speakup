# 场景题人工评测集

这里评测“题目本身值不值得让用户开口”，不评测用户回答后的纠错质量。纠错任务仍在 `evals/tasks/`。

## Pilot v1 长什么样

第一版不是 24 个互不相关的题，而是 8 个 `domain × subId × kind × difficulty` 坐标，每个坐标放一个三元组：

- `positive`：人工确认的好题，应通过硬规则且 8 维平均分不低于 4、单项不低于 3。
- `negative`：故意做坏，既包含考试腔、抽象 points、重复、过长等硬失败，也包含“字段全对但仍然无聊”的纯语义失败。
- `boundary`：真实但容易有分歧，例如难度是否标低、文化语气、医学安全、隐私措辞或成功终态是否开放。

每条样本包含：

- 实际候选题 `candidate`；
- 它在测什么 `challenge`；
- 8 维人工分数；
- 预期硬规则失败项；
- `pass / fail / borderline` 结论、失败标签和人工理由；
- 可选 `referenceIds`，用于检验与已有题的近重复。

Pilot v1 覆盖旅行、工作、社交、餐饮、医疗、银行、住宿、通讯 8 个领域，共 24 条。先让产品所有者审阅 rubric 和样本分歧，再扩到 40–60 条，避免一开始批量生产错误标签。

## 运行

```bash
cd server
uv run python -m evals.scenario_dataset

review_dir="$(mktemp -d "${TMPDIR:-/tmp}/speakup-scenario-review.XXXXXX")"
trap 'case "$review_dir" in "${TMPDIR:-/tmp}"/speakup-scenario-review.*) rm -rf "$review_dir" ;; esac' EXIT
uv run python -m evals.scenario_review --output "$review_dir/pilot-v1.html"
open "$review_dir/pilot-v1.html"
```

校验器会检查 schema、样本 ID、三类配比、8 维分数、pass/fail 门槛，并把 `expectedHardFailures` 与 `scenario_quality.grade_scenario()` 的实际结果逐条比对。
