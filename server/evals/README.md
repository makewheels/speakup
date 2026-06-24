# SpeakUp 评测集（evals/）

按 [Anthropic Engineering: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
的 8 步法搭的最小可跑版——给 `services/corrector.py` 的 LLM 判题做 end-to-end 验证。

## 跑一次

```bash
cd ~/workspace/learning/speakup/server
source .venv/bin/activate     # 或 uv run python -m evals.run ...
python -m evals.run --suite regression --trials 3
```

输出：
- 终端：每条任务 pass@k / pass^k + 总览
- `/tmp/speakup-evals-report.html`：白底单页报告，每条任务可展开看完整 LLM 原文 + 每个 grader 的判定理由

## 目录

```
evals/
├── harness.py              # 直接调 services.corrector.correct_text，不经 mongo
├── graders/
│   ├── schema.py           # 确定性：JSON/字段/语种/枚举/score 步进/better⊂nativeVersion
│   └── expectation.py      # 任务级断言：gaps_count / first_gap_category / progress_verdict ...
├── run.py                  # CLI
├── report.py               # HTML 报告
└── tasks/
    ├── regression/         # 8 条已校准的，应当近 100% 过
    └── capability/         # （留空）放难任务、新发现的失败案例
```

## 任务文件格式

每个 task 是一个 JSON 文件，schema 见 `harness.py` 的 `Task` 类：

```json
{
  "id": "task-completed-coffee",
  "desc": "咖啡店重做拿铁 — 任务完成、地道",
  "input": {
    "text": "Excuse me, this is iced — could you remake it as a hot latte? I'm in a rush.",
    "scenario": {
      "where": "☕️ 咖啡店",
      "story": "你点的热拿铁被做成了冰美式",
      "mission": "让店员重做并表明你赶时间"
    }
  },
  "expectations": [
    {"type": "schema_valid"},
    {"type": "no_task_gap"},
    {"type": "score_at_least", "value": 6.5}
  ]
}
```

支持的 expectation 类型见 `graders/expectation.py`。

## 关键指标

- **pass@k**：k 次试验中至少 1 次过 → 适合"模型能不能做到"
- **pass^k**：k 次试验全过 → 适合"用户每次能不能稳定拿到"
  - SpeakUp 是面向最终用户的产品，**回归集用 pass^k 严判**

## 加新任务

发现 bug → 写成一个 `tasks/regression/*.json`（如果已校准）或 `tasks/capability/*.json`（如果模型还做不到）。
"failed to detect X" 这类是最值钱的——直接当 regression case。
