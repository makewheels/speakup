# 公共题库主题坐标系（scenario taxonomy）

> 给所有 AI agent 看的：**公共题不是手工在聊天里写的，是系统按 yaml 坐标自动调 LLM 生成的**。
> 改 yaml = 改"题库覆盖蓝图"；要新主题就加一行 yaml，等系统自动补。

## 为什么要这套东西

公共题库需要"覆盖中国成年人日常英语用得到的处境"，**LLM 不能当编辑**——交给它自己挑主题，它会反复往"咖啡店做错单"、"机场退票"几个高频场景上撞，长尾主题永远写不到。所以：

| 角色 | 决定什么 |
|---|---|
| **人**（yaml 文件） | 域 / 子场景类型 / kind / 难度——**坐标系** |
| **LLM** | 具体冲突 / 人物 / 时间 / 地点 / 台词压力点——**剧本** |
| **系统** | 检测哪个坐标缺货、自动调 LLM 补、入库——**调度器** |

## 文件位置

- **坐标系**：`server/data/scenario_taxonomy.yaml`（16 大类 × 67 子场景）
- **生成逻辑**：`server/services/scenario_service.py` 的 `topup_public_scenario()`
- **自动触发**：`server/routes/scenarios.py` 的 `_maybe_topup`（用户取题时顺带跑）
- **手动 bootstrap 脚本**：`server/scripts/generate_public_scenarios.py`

## yaml 结构

```yaml
target_per_sub: 2  # 每个 sub 公共池目标数量；达到就停止生成

domains:
  - domain: 旅行出行         # 中文显示名
    short: travel             # 英文短名（写进 scenarios.category.domain）
    sources: [IELTS-P1-Travel]  # 灵感来源（注释用，不进库）
    subs:
      - id: travel.airport_checkin   # 全局唯一 ID（写进 scenarios.category.subId）
        sub: 机场值机柜台              # 中文场景名
        kind: task                    # task / chat / describe / opinion / explain
        difficulty: 2                 # 1 / 2 / 3
        note: 行李超重 / 改签 / 升舱   # 提示 LLM 这类场景的典型冲突
        # 可选字段：
        # bonus_zh: true              # IELTS/CEFR 不覆盖、专为中国人补的处境
        # target: 3                   # 覆盖 target_per_sub 默认值
```

## 自动生长流程

```
用户访问 GET /api/scenarios/next
    ↓
routes/scenarios.py: _maybe_topup(userId)  ← fire-and-forget 后台任务
    ↓
    ├─ 1) 用户定制题：错题本驱动（已有逻辑，不动）
    │
    └─ 2) 公共池补缺：
        ↓ undercovered_subs()
        ↓ 读 yaml + 聚合 scenarios 集合 → 找出 actual<target 的 sub
        ↓ 按 (gap 大优先，同 gap 内 shuffle) 排序
        ↓ 按 subId 获取 Mongo 生成租约，锁内重查 actual<target
        ↓
        ↓ topup_public_scenario(coord)
        ↓ 带同坐标已有题反例让 LLM 编故事 → 近重复检查 → 可选生图 → 入库
        ↓
        所有 sub 达 target → undercovered_subs 返回空 → 自动短路停止花钱
```

## 怎么扩容（**改 yaml，不改代码**）

加一个新主题：

```yaml
- id: hobby.cooking_chinese
  sub: 教外国朋友做一道中国家常菜
  kind: explain
  difficulty: 2
  bonus_zh: true
  note: 食材替代 / 火候 / 调味顺序
```

存盘。**不需要重启服务**（`load_taxonomy()` 每次调用都重读 yaml）。下一次有用户取题，系统就会补这个新坐标，最多补 `target_per_sub` 道。

## 怎么调质量

**LLM 出来的题不满意时改的不是 LLM**，是 prompt（`PUBLIC_GEN_PROMPT` 在 `scenario_service.py`）。改 prompt 后：

```bash
cd server
uv run python scripts/generate_public_scenarios.py --dry-run --count 10
```

`--dry-run` 只调 LLM 拿文案，**不调万相、不入库**——便宜，可以反复跑直到 prompt 调到满意，再去掉 `--dry-run` 真跑。

## 本地 → 生产同步（待实现）

LLM 文案 + 万相图都要花钱。**生产不该重生成**——本地 dev DB 跑出来的题，文档同步到生产 MongoDB；图存 OSS（本地/生产共用同一个 cn-beijing bucket，imageKey 直接复用）。

计划脚本：`server/scripts/sync_public_scenarios.py`（TODO）

```bash
# 本地 dev 生成
APP_ENV=development uv run python scripts/generate_public_scenarios.py --count 10

# 同步到生产（图已在 OSS）
uv run python scripts/sync_public_scenarios.py --to prod
```

## 给 agent 的注意事项

1. **不要在聊天里手工编题目** — 你写得再好都是一次性的，且会让自己变成内容瓶颈。改 yaml 让系统自动跑。
2. **不要让 LLM 自己挑主题** — 模式坍塌，永远是"咖啡店"、"机场"那几个。坐标必须由 yaml 给死。
3. **改 yaml 时不要碰已有 sub 的 `id` 字段** — 它写进了 scenarios.category.subId，改 ID 会让旧题找不到归属，覆盖统计错乱。要重命名先 inactive 老题、加新 sub。
4. **加 sub 不影响老题** — yaml 里删一个 sub 不会自动 inactive 老题，需要单独清理。
5. **dry-run 是便宜的安全检查** — 改 prompt / 加 sub 后必跑一次 dry-run 看文案，再花生图钱。
6. **不要绕过生成租约** — `actual<target` 的统计不是写入锁；任何新补题入口都必须在同一个 `subId` 租约内重查数量后再生成。

## 设计选型笔记

- **同 gap 内 shuffle**：避免空池子时所有用户都先生成 `bank.*` / `biz.*`（字母序前缀）；不同 gap 之间确定性（缺得越多越先补）。
- **target=2**：单 sub 出 2 道防"用户做完就没了"，又不至于多到无聊。要更丰富改 yaml `target_per_sub` 或个别 sub 加 `target: 3`。
- **kind 比例**（task 48% / chat 16% / describe 10% / explain 13% / opinion 12%）：日常英语办事场景天然多，task 偏高合理；chat 含 small talk 寒暄足量；describe 砍了 IELTS 凑数题（描述自行车 / 字典 / 梦境）。
- **本土化 16 道（24%）**：火锅 / 春节亲戚 / 996 / 微信支付 等 IELTS 永远不考但中国人天天遇到。

## 相关文件

- `docs/design/schema.md` — scenarios 集合 schema（含 `category` 字段）
- `docs/design/scenario-mode.md` — 场景模式总览（前端→后端→AI）
- `CHANGELOG.md` 2026-06-19 段落 — 这套坐标系的引入记录
