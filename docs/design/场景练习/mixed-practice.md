# 混合练习 · 新旧题混排与 6.5 收纳设计

> 状态：设计稿，大部分未实现。目标：练习流里新题与错题自然混排，用户无感切换；错题练到 6.5 分即收纳，不再出现。
>
> 进展（2026-08-18）：§1 的 `status: active|retired` 字段已落地，但收纳触发走的是**复习卡自查「会说」**（`retiredBy="self"`），不是本文的 6.5 达标；列表过滤、恢复、出题取材排除 retired 均已实现。本文剩余部分（混排、6.5 收纳判定）仍未实现。

## 背景

当前是两条分离的线：

- **练习流**（`/practice`）：`scenario_service.next_scenario` 派题——自己的未练定制题 > 未练公共题 > 随机公共题。定制题由 `generate_custom_scenario` 后台生成，取材是 reviewItems 里 `nextReviewAt` 最早的 3 个表达（**不区分是否到期**）。
- **复习页**（`/review`）：表达式闪卡，SM-2 调度（`nextReviewAt` / `interval` / `easiness`），前端派生状态：`isMastered = reviewCount>=3 && interval>=7`，`isDue = nextReviewAt<=now && !mastered`。

问题：用户想"一会新的一会旧的"自然练习，而不是主动去复习页刷卡；且掌握了的错题应该永久退场，现在 mastered 只是前端标签，仍占复习队列。

## 目标 / 非目标

**目标**

1. 练习流自动混入"错题题"（针对到期复习表达的定制题），与新题交替。
2. 错题题练到 IELTS ≥ 6.5 且目标表达确实用上 → 对应 reviewItem 收纳（retired），闪卡队列与出题取材都不再出现。
3. 复习页保留，但变成"兜底 + 查看"入口，不再是主要复习动作。

**非目标**

- 不改 SM-2 基础调度（闪卡路径行为不变）。
- 不做用户可配置的混排比例（先固定默认值，观察数据再调）。

## 设计

### 1. reviewItems 增加 status 字段

```json
"status": "active | retired"   // 缺省/历史数据按 active
```

- `retired` 的项：不出现在闪卡 due 队列、不计 dueCount、不被定制题取材；复习页折叠进「已收纳」区（可展开查看，可手动恢复 active）。
- 收纳来源只有两条：练习流达标（主路径）、闪卡 `isMastered` 派生条件满足时后端顺手落库（辅路径，统一状态）。

### 2. 混排策略（next_scenario 加一层）

每次派题时决定本轮出"错题题"还是"新题"：

- 条件：用户有 **到期且 active** 的 reviewItem（`nextReviewAt <= now`）。
- 节奏：每 2 道新题插 1 道错题题（用 practiceSessions 计数或用户级游标实现，不引入新集合；首版可直接 `已派新题数 % 3 == 2` 判定）。
- 错题题取材：只从 **到期 active** 项里取最早 3 个（替换现在"不区分到期"的取材），复用 `_build_scenario_doc` 反向出题；未练的定制题优先复用（现状已如此）。
- 无到期项时完全走现状逻辑，零行为变化。

用户视角：练习流里偶尔出现一道"似曾相识"的题（针对他之前说错的表达），不额外标注；可选地在场景卡上加一个小角标「复习」，首版不做。

### 3. 收纳判定（6.5 收纳）

错题题（scenario 带 `targetWords`）的 attempt 结束后判定：

- **分数条件**：`attempt.score >= 6.5`。
- **使用条件**：targetWords 里**每个**表达被用上。判定首版用宽松字符串匹配：transcript 小写后包含表达的核心片段（去掉情态/礼貌外壳，取最长实词连续串，如 "remake this"）。匹配不上的表达不收纳，下次继续出。
- 满足两者 → 该题 `targetWords` 对应的 reviewItems 全部 `status=retired`，写 `retiredAt` + `retiredBy="practice"`。
- 不引入新的 LLM 判定（成本与延迟都不可接受）；字符串匹配误判方向是"少收纳"，安全。

### 4. 数据与接口改动清单

| 位置 | 改动 |
|------|------|
| `schema.md` reviewItems | 加 `status` / `retiredAt` / `retiredBy` |
| `routes/review_items.py` list | 默认过滤 `status != retired`，加 `?includeRetired=true` |
| `routes/review_items.py` review | 闪卡达标时落 `status=retired`（辅路径） |
| `scenario_service.generate_custom_scenario` | 取材改为到期 active 项 |
| `scenario_service.next_scenario` | 混排节奏层 |
| `routes/correct.py` `_save_attempt_and_review` | attempt 落库后跑收纳判定 |
| `ReviewPage.jsx` | 「已收纳」折叠区 + 恢复按钮 |

### 5. 分期

- **P1**：status 字段 + 收纳判定 + 复习页已收纳区。不混排，行为变化最小，先验证"6.5 收纳"判定质量（看 Langfuse 里 retired 的题 transcript 是否真用上了表达）。
- **P2**：next_scenario 混排层。
- **P3**（可选）：场景卡「复习」角标、混排比例数据化调参。

### 6. 兼容与风险

- 历史 reviewItems 无 `status` → 查询按 active 兼容（`{"status": {"$ne": "retired"}}` 对缺字段成立）。
- 定制题生成有 LLM + 可选生图成本；混排不新增生成量（取材换源而已），pending 上限（MAX_PENDING_CUSTOM=2）继续生效。
- 风险：到期项长期练不到 6.5 → 反复出同一批定制题。缓解：同一表达连续 3 次未收纳则间隔翻倍（复用 interval 字段），并在复习页闪卡路径兜底。

## 待决问题

1. 混排节奏首版定 1:2（错:新），是否需要按用户水平自适应？先固定，看数据。
2. 「已收纳」区要不要支持批量恢复？首版只做单条恢复。
