# 贡献指南

面向所有贡献者（人 + AI agent）。AI agent 的项目硬上下文（敏感信息 / 部署 / SSH 等）在 [AGENTS.md](AGENTS.md)，跟开发流程无关。

## 每次改动的标准流程

```bash
# 1. 从 master 开新分支
git checkout master && git pull
git checkout -b <type>-<slug>   # feat-xxx / fix-xxx / chore-xxx / docs-xxx（分支名不含斜杠：CI 镜像文件名会用分支名）

# 2. 改代码

# 3. 跑测试（必须全绿才能提 PR）
cd server && uv run pytest tests/ -q          # 后端全套
cd web && pnpm test                           # vitest（前端行为测试，任何改动都要跑）
cd web && pnpm test:coverage                  # 覆盖率门槛检查（lines/functions/statements≥60%，branches≥50%）
cd web && pnpm run build                      # 前端构建（捕捉类型/import 错误）

# 4. 在 docs/changelog/ 追加一个 markdown 文件（每次修改一个文件，见下方格式）

# 5. 提 PR
git add <files> && git commit -m "type: 简短描述"
gh pr create --title "..." --body "..."

# 6. 自测通过后自行 merge
gh pr merge <number> --merge --delete-branch
git checkout master && git pull
```

## 测试分层规范

| 层 | 位置 | 用途 | 外部依赖 |
|----|------|------|----------|
| unit | `server/tests/unit/` | 纯逻辑、解析、ID 生成、service 函数 | 全 mock（httpx / OSS / DB） |
| integration | `server/tests/integration/` | HTTP 路由 + 真实 MongoDB | test DB（speakup-test），OSS / AI 全 mock |
| frontend | `web/src/**/*.test.jsx` | React 组件逻辑 | vitest + jsdom |

**关键约束：**
- `conftest._no_real_llm` fixture 默认 stub 所有外部出口（LLM / 万相 / CosyVoice / ASR / OSS upload），任何测试都不该真调外部接口；要测真路径在测试体内 patch 解开。
- async 函数的单元测试：mock `get_db()` 返回 `MagicMock` 避免 Motor 事件循环冲突，用 `pytestmark = pytest.mark.asyncio`。
- **前端每个页面和有状态组件必须有对应的 `.test.jsx`**，覆盖 happy path + 关键交互；新增页面/组件时同步新增测试文件。

## 工程规则（任何人写代码都要守）

- **页面的关键状态必须可被 URL 还原**：进入一个新视图 / 子状态（如练习的"结果 / 反馈页"）时，URL 要跟着变（path 段或 query param），且刷新后能从 URL + 后端数据重建该状态——绝不能"刷新就回到初始态、结果没了"。数据已落库的（如 attempt）刷新时从库里重建，不要只存内存。
- **测试要是代码**：不靠 curl 一次性脚本。
- **源码不超过 500 物理行**：前端 `pnpm run lint:lines` 递归检查 `web/src/**` 与 `web/scripts/**` 的 CSS/JS/JSX/TS/TSX；后端 `uv run python scripts/check_code_quality.py` 对业务源码查行数+参数个数、对 `tests/` 与 `scripts/` 只查行数。两者均已接入 CI。`App.css` 只负责按顺序导入 `styles/app/*.css`，后面的文件允许有意覆盖前面的选择器，拆分或重排时必须保持级联顺序并运行生产构建。超限时按主题拆文件，不允许删空行、压缩代码或豁免存量文件绕过。
- **批量调 LLM / 文生图很贵**：默认一次 ≤5 个；先 `--dry-run` 验证文案，再花生图钱。详见 `docs/design/场景练习/scenario-taxonomy.md`。
- **文档随代码一起改**：`docs/业务/*.md` 记录**当前已实现**行为（一个模块一篇），任何对外行为变更必须在同一次 PR 里同步更新对应业务文档（没有就新建一篇）+ 在 `docs/changelog/` 追加本次修改的 markdown 文件（每次修改一个文件）；数据模型变更同步 `docs/design/schema.md`。设计稿（`docs/design/`）落地后回写进展。changelog 内容按大小拿捏：小改动几行写清楚，大功能自然补背景/权衡/验证，不套固定模板（见 `docs/changelog/README.md`）。文档地图见 `docs/README.md`。

## 新增服务 / 路由时的 checklist

- [ ] 单元测试覆盖核心逻辑（mock 外部依赖）
- [ ] 集成测试覆盖 happy path + 边界（404、重复等）
- [ ] `docs/业务/*.md` 同步更新（行为变更必选；新模块新建一篇）
- [ ] `docs/design/schema.md` 同步更新（如有新集合或字段变更）
- [ ] `docs/design/storage.md` 同步更新（如有新 OSS 路径）
- [ ] `docs/changelog/<YYYYMMDD-HHMMSS>-<名字>.md` 追加本次修改记录（只增不改）
- [ ] 对应 `.test.jsx` 覆盖新增页面 / 组件的 happy path 及关键交互（前端改动必选）
- [ ] `pnpm test` 全绿，`pnpm test:coverage` 门槛通过（前端改动必选）
- [ ] `pnpm run build` 通过（如有前端改动）

## CHANGELOG 格式

**每次修改一个 markdown 文件**，平铺在 `docs/changelog/`，命名 `<YYYYMMDD-HHMMSS>-<名字>.md`——时间为**北京时间 UTC+8**，秒从 git 提交时间取（`TZ='Asia/Shanghai' git show -s --format=%cd --date=format-local:'%Y%m%d-%H%M%S'`）。内容按大小拿捏：小改动几行写清楚；大功能自然补背景/权衡/验证，不套固定模板。只增不改。索引见 `docs/changelog/README.md`。

```markdown
<!-- 文件名：20260619-160312-cost-guard-加严.md -->
# test：测试 cost-guard 加严

- 时间：2026-06-19 16:03:12（北京）
- 关联 PR：#NNN

（小改动写到这就够；大功能再自然补背景/权衡/验证。）
```

## 仓库约定

1. **每次改动都开 PR**（不直接 push master）。
2. **中文优先**：PR / commit / CHANGELOG / 文档 / 对话回复用中文，代码标识符和技术术语保持英文。
3. **不要把 IP / 主机名 / 凭据 / 密钥写进任何入库文件**（含 commit message、CHANGELOG、PR description）。具体存放位置见 [AGENTS.md](AGENTS.md#敏感信息存放约定)。
