# SpeakUp — AI 英语口语练习应用

看场景题 → 开口说英语 → AI coach 给反馈（gaps 差距 + native version + 追问 coach）→ 沉淀复习项。场景配图可选（`IMAGE_ENABLED=false` 默认关闭）。生产域名不入库（属配置，见 DNS 控制台 / 部署配置）。

> 本文件遵循 [AGENTS.md](https://agents.md) 约定，是面向所有 AI agent（Claude Code / Cursor / 其他）的项目说明。`CLAUDE.md` symlink 到这里。

## 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | React 19 + Vite 8 | SPA, pnpm 管理 |
| 后端 | FastAPI + uv | Python 3.14, 异步 |
| 数据库 | MongoDB | 本地 localhost（生产已下线）|
| 场景配图 | 火山方舟 Agent Plan Seedream（env `IMAGE_*`）| 题库预生成 + 定制题后台生成，存 OSS。**成本高，`IMAGE_ENABLED=false` 默认关闭**，新题按无图渲染 |
| 语音 ASR + TTS | 阿里云百炼 Qwen（env `VOICE_*`）| 录音转写 + nativeVersion 朗读 |
| AI 评估 | DeepSeek 官方 `deepseek-v4-flash`（env `CHAT_*`）| 场景文案 + 口述文本 → JSON 反馈，SSE 流式。换厂只改 `.env` 值不改名 |
| 部署 | Docker + ACR + Caddy | GitHub Actions 通过 OIDC 从 Infisical 取配置，push→构建→推 ACR `b4/speakup`→SSH compose up；生产域名和凭据均不进 GitHub Secrets |

## 项目结构

```
speakup/
├── web/                    # React 前端 (pnpm)
│   └── src/
│       ├── api/client.js            # fetch 封装
│       ├── context/UserContext.jsx   # 登录状态 (localStorage)
│       ├── pages/                    # Login, Practice, Feedback, Review, History, SessionDetail, Profile, Share 等
│       └── components/layout/        # 底部导航
├── server/                    # FastAPI 后端 (uv)
│   ├── main.py                      # 入口, lifespan 初始化
│   ├── config.py                    # 按 APP_ENV 加载 .env
│   ├── db/connection.py             # Motor async MongoDB
│   ├── services/
│   │   ├── corrector.py             # LLM 按场景评估口语（三轮 progress 对比）
│   │   ├── scenario_service.py      # 派题 + 因材施教定制题后台生成
│   │   ├── wanx.py                  # 场景文生图（默认 Seedream；文件名沿用历史）
│   │   ├── oss_storage.py           # 阿里云 OSS 底层封装（私有桶，只存 key 读时现签）
│   │   └── ...                      # 另有 transcriber / tts / translator / followup_chat / scenario_images 等
│   ├── routes/                      # auth, scenarios, correct, practice_sessions, review_items, feedbacks, transcribe, tts
│   ├── utils/
│   │   └── id_generator.py          # 业务 _id 前缀：u_ / ps_ / rv_ / sc_ / llm_ / fb_
│   └── tests/
│       ├── conftest.py              # 测试 DB 初始化 + cost guard fixture
│       ├── unit/                    # 纯逻辑单元测试，全 mock，毫秒级
│       └── integration/             # 走 HTTP + 真实 test DB，秒级
├── docs/                    # 文档（地图与维护约定见 docs/README.md）
│   ├── 业务/                # 「当前已实现」行为的分模块文档（如 1-错题本与复习.md）
│   ├── deploy.md            # 部署指南（架构/首次部署/回滚/运维命令）
│   ├── evals.md             # 评测方法与历次基线记录
│   ├── langfuse.md          # Langfuse 自托管部署与埋点
│   ├── scenario-evaluation.md # 题目评测方案（8 维/模拟器/发布门禁）
│   └── design/              # 设计稿 + 数据模型（改动涉及 schema/存储/ID 时同步更新）
│       ├── spec.md          # 产品功能文档（定位/用户旅程/逐页 UI 规格）
│       ├── schema.md        # MongoDB 集合 schema（数据模型事实源）
│       ├── ids.md           # ID 规范
│       ├── storage.md       # OSS 路径设计
│       ├── scenario-mode.md # 场景模式总览（流程/模型/存储/后台任务）
│       ├── scenario-taxonomy.md # 公共题分类与 LLM 批量生成流程
│       └── mixed-practice.md    # 混合练习设计稿（部分已实现，见文首状态）
├── design/                  # UI 设计稿画布原型（SpeakUp.html，非运行代码）
├── Dockerfile               # 多阶段构建（pnpm 前端 + uv 后端）
├── docker-compose.yml       # 生产业务服务（Caddy 网关在服务器 /opt/caddy，不入库）
└── .github/workflows/       # ci-cd.yml（构建部署）+ evals.yml（手动触发评测）
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

- **UI 文案走 i18n（zh-CN / en）**：新增/修改 UI 文案必须走 `web/src/i18n/` 字典；默认跟随浏览器语言，用户可在 Profile → 设置切换；选择存 localStorage，不入库（属个人偏好）。代码注释仍用中文。AI 输出（gaps/nativeVersion/summary）保持中文不动——这是另一坨工作，跟 corrector prompt 和场景库捆绑，需要另起 PR。
- 语音识别走全平台 MediaRecorder + 后端百炼 Qwen ASR
- 云 ASR 失败时前端允许手动补录转写继续评估；云 TTS 失败时降级浏览器 `speechSynthesis`。这是可用性兜底，运维验收仍须分别实测 `/api/transcribe` 与 `/api/tts`
- AI/自动化生产体验必须先用 `POST /api/auth/login` 创建 `sourceType=ai_test` 的专用账号，再用该账号走页面；不得用普通 `human` 账号产生测试数据
- `.env` 文件不在版本控制中
- pnpm 全局 store: `~/Library/pnpm/store/v10`
- uv 全局 cache: `~/.cache/uv`
- **不要重复启动 dev server**：前端默认跑在 :5173，启动前先 `lsof -ti :5173` 检查是否已有进程；有则直接用，不要再 `pnpm run dev`
- **开工先 pull**：开分支前必须 `git checkout master && git pull`（CONTRIBUTING 标准流程第 1 步），不得基于过时本地 master 开分支或合并；多 agent/多机协作时本地 master 经常是旧的
- 部署详情见 `docs/deploy.md`（回滚、多服务约定、运维命令）
- 开发流程 / 测试分层 / CHANGELOG 格式 / PR 约定 见 [CONTRIBUTING.md](CONTRIBUTING.md)（人 + agent 共用）

## 已知不足（待迭代）

- 登录：手机号直接注册无验证，无 token（MVP 自用阶段）
- production HTTPS 依赖 Caddy + Let's Encrypt（域名由 Infisical 注入）；腾讯云 443 端口的 TLS 阻断问题(旧生产被迫走 8443)是否影响新机待部署后实测
- 内网 DB 连接依赖 Lighthouse 同 VPC（已确认 services→DB 机的 27017 通）

---

# 给 agent 的操作信息

## 敏感信息存放约定

**不要把 IP / 主机名 / 凭据 / 密钥写进任何入库文件**（包括本文件、commit message、CHANGELOG、PR description）。

具体值的存放位置：

| 类型 | 位置 |
|------|------|
| 生产 SSH host / user / 内网 IP | Infisical `speakup/prod/deployment` 与 `speakup/prod/db` |
| 文字 / 图片 / 语音 / 视频 LLM Key | Infisical `speakup/<env>/llm`；跨项目共用值从 `common` 后加载覆盖 |
| MongoDB 连接串 | Infisical `speakup/<env>/db` |
| OSS / Langfuse | Infisical `speakup/<env>/oss`、`speakup/<env>/langfuse` |
| SSH 与 ACR 凭据 | Infisical `speakup/prod/deployment`；仅在流水线临时目录中落盘 |

GitHub 仓库只保留非敏感的 Infisical endpoint/audience Actions Variables；`gh secret list` 应为空。

## 部署运维

部署详情见 `docs/deploy.md`。要点：

- 生产机：Tencent Lighthouse "services" (Ubuntu 24.04)，多服务架构：
  - `/opt/caddy/` 是**唯一**占 80/443 的网关，独立 compose + Caddyfile
  - `/opt/speakup/` 业务服务，不暴露宿主端口，通过 docker external network `edge` 与 caddy 通信
  - 加新服务：业务 compose 接 edge network → Caddyfile 加一段 reverse_proxy → caddy reload
- `docker compose -f /opt/speakup/docker-compose.yml logs -f` 看业务日志；`/opt/caddy/...` 看网关日志
- 回滚：旧 `:latest` 每次部署转 `:previous`，`docker tag :previous :latest && docker compose up -d` 回退一步
- 镜像仓库：阿里云 ACR 个人版 cn-beijing，路径 `registry.cn-beijing.aliyuncs.com/b4/speakup`，登录凭据从 Infisical 临时注入。caddy 等公共镜像走 docker.io（生产机 daemon 配 `registry-mirrors` 加速）

## HTTPS

- 当前实测：services 机的 443 端口正常通，Caddy 自动 Let's Encrypt（旧机有过 443 阻断走 8443 的历史，新机没复现）
- 域名从 Infisical 注入，由 `/opt/caddy/Caddyfile` 配置（不入库）

## 凭据旋转 checklist

凭据如果在以下任一处出现过，**应立即旋转**：

- [ ] git commit message / diff / PR description / issue 描述
- [ ] AI 对话历史（chat 记录、聊天截图）
- [ ] Slack / 飞书 / 微信 等 IM 同步过
- [ ] 工单 / 任何外部系统

旋转步骤：

- MongoDB 密码：连进 mongo `db.changeUserPassword(...)` → 更新 Infisical `speakup/<env>/db` → 跑流水线验证
- Agent Plan key：在供应商控制台轮换 → 更新 Infisical `speakup/<env>/llm` → 跑相应环境验证
- SSH key：生成专用 CI key → 腾讯 Lighthouse 更新公钥 → 更新 Infisical `speakup/prod/deployment` → 成功后移除旧公钥
