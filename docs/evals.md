# 评测集（evals）

end-to-end 评估 `server/services/corrector.py` 的 LLM 判题——给 prompt / 模型 / schema 改动加一层底线，防止退步。

## 三句话总结

- **不 mock**：直接调真实 corrector，跑真实 LLM 调用
- **regression 严判，capability 看上限**：用 `pass^k`（k 次必须全过）和 `pass@k`（k 次至少 1 过）区分"底线 vs 趋势"
- **任务全部来自真实失败**：14 条 capability 全部抠自 prod `llmCalls`；12 条 regression 是已校准的标杆，配合 prod 真实场景

跑法 / 目录结构 / 任务 schema → `server/evals/README.md`。

## 基线记录

### 2026-08-13 百炼 5 模型横评（regression 12 × 3 trials）

用 `evals.compare` 跑的新口径基线。背景：生产 CHAT 临时切在 DeepSeek 官方（百炼 key 曾 401），
本次验证各模型在纠错任务上的真实表现：

| 模型 | pass@3 | pass^3 | 平均分 | 平均延迟 | 结论 |
|---|---|---|---|---|---|
| **glm-5.2** | 11/12 | **8/12** | 4.76 | **3.3s** | ✅ 仍为最佳，建议作为生产首选 |
| qwen3-max | 10/12 | 7/12 | 4.14 | 5.0s | 🟡 次选，贵且慢一些 |
| glm-4.7 | 10/12 | 6/12 | 4.56 | 3.6s | 🟡 便宜档可用 |
| kimi-k2.6 | 10/12 | 5/12 | 4.50 | 5.1s | 🟡 百炼上延迟正常（旧火山 plan 的 270s/条是 provider 问题） |
| **deepseek-v3.2**（≈当前生产 deepseek-chat） | 8/12 | 5/12 | 3.52 | 5.0s | ❌ 核心能力塌陷 |

deepseek-v3.2 的失败集中在核心纠错能力：`grammar-past-tense-go` 0/3（挑不出 go→went）、
`vocab-borrow-vs-lend` 0/3、`boundary-chinese-only` 0/3——**当前生产模型处于质量回退状态，
百炼 key 恢复后应切回 glm-5.2**。

各模型盲区不一致，值得一看的交叉点：glm-5.2 独挂 `chinglish-redundant-me`（0/3，其他模型能过），
deepseek/qwen 挂 borrow/lend 而 glm/kimi 稳过；`scoring-anchor-low` 对全员最难（灰区评分锚点
仍是已知弱项）。

同批 capability（14 × 1 trial，prod 真实失败案例，单 trial 噪音大、只看趋势）：

| 模型 | pass@1 | 平均分 | 平均延迟 |
|---|---|---|---|
| glm-5.2 | **11/14** | 4.86 | 5.0s |
| glm-4.7 | 10/14 | 4.79 | 4.6s |
| deepseek-v3.2 | 7/14 | 3.68 | 6.6s |
| kimi-k2.6 | 6/14 | 4.46 | 8.0s |
| qwen3-max | 4/14 | 4.42 | 8.1s |

glm-5.2 在两个集子上都是第一；对比 2026-06-24 的 capability 7/14，prompt 迭代把 prod
失败案例通过率推到了 11/14。

### 2026-08-09 百炼 `glm-5.2` 恢复基线

迁移到阿里云百炼并修复中文 fast-path 后，完整 regression 跑 `3 trials × 12`：

| 指标 | 结果 | 说明 |
|---|---|---|
| pass@3 | 12/12 = 100% | 所有能力都能稳定触达，不再有完全做不到的 case |
| pass^3 | 9/12 = 75% | 仍有 3 条随机性失败：过度纠风格、summary 偶发超长、个别 better 没落到 nativeVersion |
| 纯中文边界 | pass^3 | 从旧 fast-path/假高分改为 task gap + `score<=2.0` |

这是当前发布基线，不应把 `pass@3=100%` 误读成已经稳定；面向用户的主指标仍是 `pass^3`。

### 2026-06-24 首次基线

使用 `glm-5.2`，3 trials × 12 条 regression + 1 trial × 14 条 capability：

| 集子 | 通过 | 备注 |
|---|---|---|
| regression | pass@3 = 10/12 (83%)，pass^3 = 6/12 (50%) | 4 条不稳：summary 超长、灰区评分锚点不稳、纯中文输入误走 fastpath |
| capability | pass@1 = 7/14 (50%) | prod 真实失败 case，模型还没稳定挑出 |

## 评测方向（按 prod 数据反推的 6 大维度）

| # | 方向 | regression | capability | 真实情况 |
|---|---|---|---|---|
| 1 | 语言地道度 | 02/03/06 | 02/03/04/06/07/08/09/10/11/12 | prod 80% 错误集中于此 |
| 2 | 任务完成度 | 04/05 | 01/04/05 | corrector 区别于通用语法工具的核心 |
| 3 | 打分一致性 | 09/10 | — | prod 80% 分数落 5.0–6.0 灰区，必须测稳定性 |
| 4 | 边界输入 | 01/11/12 | — | 短/超长/中英夹杂/纯中文 |
| 5 | 多轮重说 | 07/08 | — | progress.verdict 判 stuck/improved/passed |
| 6 | 场景适配 | （融入） | 14 | 头部生产场景：机场/咖啡店/客服/急救 |

## 跨模型对比

跑 `server/evals/compare.py`（`python -m evals.compare`）做横向对比：

```bash
cd server
uv run python -m evals.compare \
  --models glm-5.2,deepseek-v3.2,qwen3-max \
  --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --api-key-env DASHSCOPE_API_KEY \
  --suite regression --trials 3
```

- 模型 spec：`name[@base_url[@KEY_ENV]]`，KEY_ENV 是环境变量名（key 不上命令行）
- `--ping` 只探活不评测；报告（HTML+JSON）默认输出到 `mktemp` 目录
- 所有调用打 langfuse `environment=eval` + `model:<名字>` tag，可按模型过滤 trace

历史结论（2026-06-24，火山方舟 Coding Plan，旧 1-trial 口径）：

| 模型 | 通过率 | 平均延迟 | 评价 |
|---|---|---|---|
| **glm-5.2** | 17/26 = 65% | 7.1 s | ✅ 当时生产模型，速度+准确率最佳 |
| **deepseek-v4-pro** | 13/26 = 50% | 33.0 s | 🟡 个别题比 glm 强但延迟 5×，不建议换 |
| **minimax-m3** | 3/26 = 12% | 25.6 s | ❌ 准确率灾难 |
| **kimi-k2.6** | 跑 3 条退出 | 270 s/条 | ❌ 延迟不可接受（首条 170s，第 2-3 条 500s+） |

## 我们照搬了 Anthropic 的哪几条原则

参考 [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)，6 条核心被落到这套框架：

1. **end-to-end 不打桩** → `harness.py:86` 直调 `services.corrector.correct_text`
2. **regression / capability 分档** → `tasks/{regression,capability}/`，前者 PR 必跑，后者看趋势
3. **pass^k 而非 pass@k** → speakup 是面向用户的产品，要的是"每次都稳"，不是"k 次蒙对 1 次"
4. **任务诊断真实失败模式** → capability 14 条全部从 prod `llmCalls` 抠出来
5. **必须有假阳性陷阱** → `regression/05-task-completed-clean.json`：任务办成时不能瞎挑 task gap
6. **确定性 grader 优先** → `graders/schema.py`（结构）+ `graders/expectation.py`（语义）分两层

唯一**还没落**的一条：博客建议"先人工标注 ground truth、再算 grader 和人类的一致性"。当前 26 条都是单人写的期望，没有交叉校验——任务长到 30+ 时需要补这一步。

## 加新任务的纪律

- 发现 prod failure → 写成 `tasks/capability/*.json`
- 稳定改对后 → 晋升进 `tasks/regression/*.json`
- **改 corrector prompt 前先看 eval 不挂**，改完跑一遍验证没退步
- 先入库锁基线再 PR 调任何东西——否则改了就分不清是模型变好还是 grader 变松了

## 还差什么

- **PR 自动跑**：`.github/workflows/evals.yml` 已提供手动触发（workflow_dispatch，百炼 key，
  报告传 artifact）；基线 pass^k 没到 100% 之前不接 PR 自动门禁，避免随机性误报
- **prod failure 自动导入**：脚本化 `llmCalls → capability/` 的管道还没写
- **AI 输出双语**：[[i18n]] 那个 PR 只翻了 UI；gaps/nativeVersion/summary 仍中文，跨语言对齐是另一坨工作
