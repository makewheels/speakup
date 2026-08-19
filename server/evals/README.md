# SpeakUp 评测集（evals/）

按 [Anthropic Engineering: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
的 8 步法搭的最小可跑版——给 `services/corrector.py` 的 LLM 判题做 end-to-end 验证。

## 跑一次

```bash
cd server   # 仓库内的 server/ 目录
uv run python -m evals.run --suite regression --trials 3
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
├── run.py                  # CLI：单配置跑基线
├── compare.py              # CLI：跨模型对比（多 trial、pass@k/pass^k、langfuse model tag）
├── langfuse_report.py      # 结果回写 Langfuse（experiment run + score，未配 env 时 no-op）
├── report.py               # HTML 报告
└── tasks/
    ├── regression/         # 12 条已校准的，应当近 100% 过
    └── capability/         # 14 条难任务 / prod 真实失败案例
```

跨模型对比（key 走环境变量，见 `compare.py` 头注）：

```bash
uv run python -m evals.compare --models glm-5.2,deepseek-v3.2 \
  --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --api-key-env DASHSCOPE_API_KEY --suite regression --trials 3
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

## Langfuse 回写（可选）

配了 `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` 时，跑完自动把结果
写回 Langfuse dev project（`langfuse_report.py`；未配时整体 no-op，不影响本地报告）：

- task ↔ dataset item 按 input 全等匹配（dataset `speakup/evals/<suite>-v1` 只是镜像，
  git 的 `tasks/` 目录才是事实源）
- 每次运行 = 一个 experiment run（名 = 模型标签 + 时间戳）；每个 task 选代表 trial
  （优先第一个失败 trial，方便点开看失败原因）挂 run item
- score：每 trial 一条 `eval-pass`（0/1，comment 带 grader 失败理由）；
  每 task 一条 `pass@k` / `pass^k`（0/1，挂代表 trial 的 trace）
- 看结果：Datasets → 数据集 → **Experiments** 标签；score 列的平均即总通过率，
  点行可跳 trace 看 LLM 原文

CI（`.github/workflows/evals.yml`）已配 `LANGFUSE_HOST`，key 走 Infisical，
手动触发即回写。本地跑要自己 export 三个 LANGFUSE_* 变量才会回写。

## 加新任务

发现 bug → 写成一个 `tasks/regression/*.json`（如果已校准）或 `tasks/capability/*.json`（如果模型还做不到）。
"failed to detect X" 这类是最值钱的——直接当 regression case。

场景题生成与纠错是两个不同的被测对象。题目确定性 grader 在
`scenario_quality.py`，完整的分层数据集、LLM judge、用户模拟和线上指标方案见
`docs/design/场景练习/scenario-evaluation.md`。

题目本身的第一版人工评测集在 `scenario_tasks/pilot_v1/`：8 个口语坐标，每组
包含正例、反例、边界例，共 24 条。运行 `uv run python -m evals.scenario_dataset`
校验数据，或用 `evals.scenario_review` 生成可筛选的本地审阅页；格式和命令见
`scenario_tasks/README.md`。
