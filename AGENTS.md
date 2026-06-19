# SpeakUp — AI 英语口语练习应用

看图片 → 说英语 → AI (VLM) 看图给反馈。生产域名不入库（属配置，见 DNS 控制台 / 部署配置）。

> 本文件遵循 [AGENTS.md](https://agents.md) 约定，是面向所有 AI agent（Claude Code / Cursor / 其他）的项目说明。`CLAUDE.md` symlink 到这里。

## 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | React 19 + Vite 8 | SPA, pnpm 管理 |
| 后端 | FastAPI + uv | Python 3.14, 异步 |
| 数据库 | MongoDB | 本地 localhost（生产已下线）|
| 场景配图 | DashScope 通义万相（env `IMAGE_MODEL`）| 题库预生成 + 定制题后台生成，存 OSS |
| AI 评估 | DashScope Qwen（env `CHAT_MODEL`）| 场景文案 + 口述文本 → JSON 反馈，SSE 流式 |
| 部署 | Docker + ACR + Caddy | GitHub Actions push→构建→推 ACR `b4/speakup`→SSH compose up；caddy 走 docker.io，靠生产机 docker daemon 配置的镜像加速器拉；生产域名走 GitHub Secret `DOMAIN`，Caddy 自动 HTTPS |

## 项目结构

```
speakup/
├── web/                    # React 前端 (pnpm)
│   └── src/
│       ├── api/client.js            # fetch 封装
│       ├── context/UserContext.jsx   # 登录状态 (localStorage)
│       ├── pages/                    # Login, Practice, Vocabulary, History, SessionDetail, Profile
│       └── components/layout/        # 底部导航
├── server/                    # FastAPI 后端 (uv)
│   ├── main.py                      # 入口, lifespan 初始化
│   ├── config.py                    # 按 APP_ENV 加载 .env
│   ├── db/connection.py             # Motor async MongoDB
│   ├── services/
│   │   ├── corrector.py             # Qwen 按场景评估口语（三轮 progress 对比）
│   │   ├── scenario_service.py      # 派题 + 因材施教定制题后台生成
│   │   ├── wanx.py                  # 通义万相文生图
│   │   └── oss_storage.py           # 阿里云 OSS 底层封装（私有桶，只存 key 读时现签）
│   ├── routes/                      # auth, scenarios, correct, practice_sessions, review_items
│   ├── utils/
│   │   └── id_generator.py          # scenario_id() → sc_ 前缀（其余集合用 ObjectId）
│   └── tests/
│       ├── conftest.py              # 测试 DB 初始化 + cost guard fixture
│       ├── unit/                    # 纯逻辑单元测试，全 mock，毫秒级
│       └── integration/             # 走 HTTP + 真实 test DB，秒级
├── docs/design/             # 设计文档（改动涉及 schema/存储/ID 时同步更新）
│   ├── ids.md               # ID 规范
│   ├── schema.md            # MongoDB 集合 schema
│   ├── scenario-mode.md     # 场景模式总览（流程/模型/存储/后台任务）
│   └── storage.md           # OSS 路径设计
│   └── deploy.md            # 部署指南
├── Dockerfile               # 多阶段构建（pnpm 前端 + uv 后端）
├── docker-compose.yml       # speakup + Caddy 自动 HTTPS
├── Caddyfile                # 自动证书 + 反代配置
└── .github/workflows/ci-cd.yml
```

## 环境隔离

| 环境 | MongoDB | 启动 |
|------|---------|------|
| dev (本地) | localhost/speakup | `uv run python main.py` |
| prod | 内网 `MONGO_URI` 指向 DB 机:27017 | Docker (`docker compose up -d`) |

环境由 `APP_ENV` 切换（dev/prod 默认 development）。`config.py` 加载 `.env.{APP_ENV}` 然后用 `.env` 兜底。

## 启动

```bash
# 本地开发
cd server && uv run python main.py     # API :3001
cd web && pnpm run dev              # 前端 :5173 → proxy /api

# 生产部署 (自动)
git push master  # GitHub Actions → 构建镜像 → 推 ACR → SSH compose up
```

## 注意事项

- 语音识别仅 Chrome (Web Speech API)
- `.env` 文件不在版本控制中
- pnpm 全局 store: `~/Library/pnpm/store/v10`
- uv 全局 cache: `~/.cache/uv`
- **不要重复启动 dev server**：前端默认跑在 :5173，启动前先 `lsof -ti :5173` 检查是否已有进程；有则直接用，不要再 `pnpm run dev`
- **页面的关键状态必须可被 URL 还原**：进入一个新视图/子状态（如练习的"结果/反馈页"）时，URL 要跟着变（path 段或 query param），且刷新后能从 URL + 后端数据重建该状态——绝不能"刷新就回到初始态、结果没了"。数据已落库的（如 attempt）刷新时从库里重建，不要只存在内存。
- 部署详情见 `docs/deploy.md`（回滚、多服务约定、运维命令）

## 已知不足（待迭代）

- 登录：手机号直接注册无验证，无 token（MVP 自用阶段）
- production HTTPS 依赖 Caddy + Let's Encrypt（域名见 GitHub Secret `DOMAIN`）；腾讯云 443 端口的 TLS 阻断问题(旧生产被迫走 8443)是否影响新机待部署后实测
- 内网 DB 连接依赖 Lighthouse 同 VPC（已确认 services→DB 机的 27017 通）

---

# 给 agent 的操作信息

## 敏感信息存放约定

**不要把 IP / 主机名 / 凭据 / 密钥写进任何入库文件**（包括本文件、commit message、CHANGELOG、PR description）。

具体值的存放位置：

| 类型 | 位置 |
|------|------|
| 生产 SSH host / user / 内网 IP | GitHub Secrets：`DEPLOY_HOST` `DEPLOY_USER` `MONGO_URI` 等 |
| DashScope API Key | GitHub Secrets `DASHSCOPE_API_KEY` + 本地 `server/.env` |
| MongoDB 连接串 | GitHub Secrets `MONGO_URI` + 线上 `/opt/speakup/server/.env` |
| SSH 私钥 | 本机 `~/Downloads/qcloud_lighthouse_beijing`（不入库）+ GitHub Secrets `SSH_PRIVATE_KEY` |

`gh secret list` 可以看到都设了哪些 secrets。

## 部署运维

部署详情见 `docs/deploy.md`。要点：

- 生产机：Tencent Lighthouse "services" (Ubuntu 24.04)，多服务架构：
  - `/opt/caddy/` 是**唯一**占 80/443 的网关，独立 compose + Caddyfile
  - `/opt/speakup/` 业务服务，不暴露宿主端口，通过 docker external network `edge` 与 caddy 通信
  - 加新服务：业务 compose 接 edge network → Caddyfile 加一段 reverse_proxy → caddy reload
- `docker compose -f /opt/speakup/docker-compose.yml logs -f` 看业务日志；`/opt/caddy/...` 看网关日志
- 回滚：旧 `:latest` 每次部署转 `:previous`，`docker tag :previous :latest && docker compose up -d` 回退一步
- 镜像仓库：阿里云 ACR 个人版 cn-beijing，路径 `registry.cn-beijing.aliyuncs.com/b4/speakup`，登录用主账号固定密码（GitHub Secret `ACR_AK_ID`/`ACR_AK_SECRET`）。caddy 等公共镜像走 docker.io（生产机 daemon 配 `registry-mirrors` 加速）

## HTTPS

- 当前实测：services 机的 443 端口正常通，Caddy 自动 Let's Encrypt（旧机有过 443 阻断走 8443 的历史，新机没复现）
- 域名走 GitHub Secret `DOMAIN`，由 `/opt/caddy/Caddyfile` 配置（不入库）

## 凭据旋转 checklist

凭据如果在以下任一处出现过，**应立即旋转**：

- [ ] git commit message / diff / PR description / issue 描述
- [ ] AI 对话历史（chat 记录、聊天截图）
- [ ] Slack / 飞书 / 微信 等 IM 同步过
- [ ] 工单 / 任何外部系统

旋转步骤：

- MongoDB 密码：连进 mongo `db.changeUserPassword(...)` → 同步改 `server/.env` 和 GitHub Secret `MONGO_URI`
- DashScope key：阿里云 RAM 控制台生成新 key → 同步两处
- SSH key：本地 `ssh-keygen` → 腾讯 Lighthouse 上传 → 删除旧 key → 更新 GitHub Secret `SSH_PRIVATE_KEY`

## 开发测试流程（agent 必读）

### 每次改动的标准流程

```bash
# 1. 从 master 开新分支
git checkout master && git pull
git checkout -b <type>/<slug>   # feat/ fix/ chore/ docs/

# 2. 改代码

# 3. 跑测试（必须全绿才能提 PR）
cd server && uv run pytest tests/ -q          # 后端全套
cd web && pnpm test                           # vitest（前端行为测试，任何改动都要跑）
cd web && pnpm test:coverage                  # 覆盖率门槛检查（lines/functions/statements≥60%，branches≥50%）
cd web && pnpm run build                      # 前端构建（捕捉类型/import 错误）

# 4. 更新 CHANGELOG.md（## [Unreleased] 段）

# 5. 提 PR
git add <files> && git commit -m "type: 简短描述"
gh pr create --title "..." --body "..."

# 6. 自测通过后自行 merge
gh pr merge <number> --merge --delete-branch
git checkout master && git pull
```

### 测试分层规范

| 层 | 位置 | 用途 | 外部依赖 |
|----|------|------|----------|
| unit | `server/tests/unit/` | 纯逻辑、解析、ID 生成、service 函数 | 全 mock（httpx/OSS/DB） |
| integration | `server/tests/integration/` | HTTP 路由 + 真实 MongoDB | test DB（speakup-test），OSS/AI 全 mock |
| frontend | `web/src/**/*.test.jsx` | React 组件逻辑 | vitest + jsdom |

**关键约束：**
- `conftest.py` 的 `_no_real_llm` fixture 会拒绝任何真实 DashScope 调用，测试里必须 mock `services.corrector._get_client`
- OSS 上传（`upload_bytes_async`）和 HTTP 下载（`httpx.AsyncClient`）在测试里必须 mock，不能打真实外部服务
- async 函数的单元测试：mock `get_db()` 返回 MagicMock 避免 Motor 事件循环冲突，用 `pytestmark = pytest.mark.asyncio`
- **前端每个页面和有状态组件必须有对应的 `.test.jsx`**，覆盖 happy path + 关键交互；新增页面/组件时同步新增测试文件

### 新增服务/路由时的 checklist

- [ ] 单元测试覆盖核心逻辑（mock 外部依赖）
- [ ] 集成测试覆盖 happy path + 边界（404、重复等）
- [ ] `docs/design/schema.md` 同步更新（如有新集合或字段变更）
- [ ] `docs/design/storage.md` 同步更新（如有新 OSS 路径）
- [ ] `CHANGELOG.md` 更新
- [ ] 对应 `.test.jsx` 覆盖新增页面/组件的 happy path 及关键交互（前端改动必选）
- [ ] `pnpm test` 全绿，`pnpm test:coverage` 门槛通过（前端改动必选）
- [ ] `pnpm run build` 通过（如有前端改动）

### 仓库工作流约定

1. **每次改动都开 PR**（不直接 push master）
2. **每个 PR 更 CHANGELOG.md**：写在 `## [Unreleased]` 段。一天多次改动按时间倒序分组，每段标题用 `### YYYY-MM-DD HH:MM`（本地时区，精确到分钟，从 commit 时间取），段下面扁平列表，前缀标类型（`add` / `change` / `fix` / `test` / `chore`）。最新放最上。
3. **测试要是代码**：不靠 curl 一次性脚本
4. **中文优先**：PR / commit / CHANGELOG / 文档 / 对话回复用中文，代码标识符和技术术语保持英文
