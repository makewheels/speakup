# 评测集（evals）

end-to-end 评估 `server/services/corrector.py` 的 LLM 判题——给 prompt / 模型 / schema 改动加一层底线，防止退步。

## 三句话总结

- **不 mock**：直接调真实 corrector，跑真实 LLM 调用
- **regression 严判，capability 看上限**：用 `pass^k`（k 次必须全过）和 `pass@k`（k 次至少 1 过）区分"底线 vs 趋势"
- **任务全部来自真实失败**：14 条 capability 全部抠自 prod `llmCalls`；12 条 regression 是已校准的标杆，配合 prod 真实场景

跑法 / 目录结构 / 任务 schema → `server/evals/README.md`。

## 当前基线（2026-06-24 首次跑）

跟用 `glm-5.2`，3 trials × 12 条 regression + 1 trial × 14 条 capability：

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

## 4 模型对比（2026-06-24，火山方舟 Coding Plan）

跑 `server/scripts/compare_models.py` 拿到的横向对比，结论：

| 模型 | 通过率 | 平均延迟 | 评价 |
|---|---|---|---|
| **glm-5.2** | 17/26 = 65% | 7.1 s | ✅ 当前生产模型，速度+准确率最佳 |
| **deepseek-v4-pro** | 13/26 = 50% | 33.0 s | 🟡 个别题比 glm 强但延迟 5×，不建议换 |
| **minimax-m3** | 3/26 = 12% | 25.6 s | ❌ 准确率灾难 |
| **kimi-k2.6** | 跑 3 条退出 | 270 s/条 | ❌ 延迟不可接受（首条 170s，第 2-3 条 500s+） |

报告（HTML）默认输出到 `/tmp/speakup-models-compare-*.html`。

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

- **没接 CI**：regression 应该 PR 必跑，目前还要手动
- **prod failure 自动导入**：脚本化 `llmCalls → capability/` 的管道还没写
- **AI 输出双语**：[[i18n]] 那个 PR 只翻了 UI；gaps/nativeVersion/summary 仍中文，跨语言对齐是另一坨工作
