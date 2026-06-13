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
| 部署 | 暂无 | 生产已下线，仅本地运行；CI 只跑测试 |

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
├── scripts/                 # 部署辅助脚本
├── .github/workflows/ci-cd.yml
└── ecosystem.config.cjs     # PM2 配置
```

## 环境隔离

| 环境 | MongoDB | 启动 |
|------|---------|------|
| dev (本地) | localhost/speakup | `uv run python main.py` |
| prod | 内网 IP / speakup | PM2 管理 |

环境由 `APP_ENV` 切换（dev/prod 默认 development）。`config.py` 加载 `.env.{APP_ENV}` 然后用 `.env` 兜底。

## 启动

```bash
# 本地开发
cd server && uv run python main.py     # API :3001
cd web && pnpm run dev              # 前端 :5173 → proxy /api

# 生产部署 (自动)
git push  # GitHub Actions → rsync → PM2 reload
```

## 注意事项

- 语音识别仅 Chrome (Web Speech API)
- `.env` 文件不在版本控制中, rsync 时排除
- pnpm 全局 store: `~/Library/pnpm/store/v10`
- uv 全局 cache: `~/.cache/uv`
- **不要重复启动 dev server**：前端默认跑在 :5173，启动前先 `lsof -ti :5173` 检查是否已有进程；有则直接用，不要再 `pnpm run dev`

## 已知不足（待迭代）

- 登录：手机号直接注册无验证，无 token（MVP 自用阶段）
- 部署系统有 secrets 不透传 + 路径错位 bug，详见下文 "部署 known issues"
- HTTPS 通过 8443 端口提供（腾讯云 443 端口被网络层拦截），HTTP 自动跳转

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

## 部署目标抽象描述

- web 实例：腾讯 Lighthouse（北京区），ubuntu 用户，PM2 + Nginx，FastAPI 在 3001
- db 实例：同区 Lighthouse，独立机器跑 MongoDB，**走内网 IP 连接**（不走公网）
- 同区 Lighthouse 之间默认内网互通（同 VPC）

## 常用命令模板

```bash
# SSH 上 web（HOST 从 gh secret 或腾讯控制台取）
ssh -i ~/Downloads/qcloud_lighthouse_beijing ubuntu@<HOST>

# 看 PM2
pm2 list
pm2 logs speakup-server --lines 50

# 改线上 server/.env（敏感值，sudo nano，不要拷贝到 chat）
sudo nano /opt/speakup/server/.env
pm2 restart speakup-server

# 强制重建 venv（rsync 推过坏 venv 时）
cd /opt/speakup/server && rm -rf .venv && uv sync
pm2 restart speakup-server

# Aliyun DNS（本机 `aliyun configure list` 已配 default profile）
aliyun alidns DescribeDomainRecords --DomainName <主域名>

# 腾讯 Lighthouse（本机 tccli 已配 default profile, region ap-beijing）
tccli lighthouse DescribeInstances --region ap-beijing
tccli lighthouse DescribeFirewallRules --InstanceId <实例 id> --region ap-beijing
```

## 部署系统 known issues

需修：

1. `deploy.yml` 写 `.env.production` 到 `/opt/speakup/`（根目录），但 `config.py` 读 `server/`。**路径错位**，secrets 实际没生效。
2. `ssh ... bash << 'REMOTE'` 单引号 heredoc + ssh 不透传 GitHub Actions runner 的 env vars，导致远端 `$DASHSCOPE_API_KEY` `$MONGO_URI` 是空字符串。
3. 现在能跑是因为 `server/.env` 是 5/24 22:00 手动放的（含真实凭据），rsync 因为 `--exclude='.env'` 没动它。

正确做法（待实现）：runner 上用 secrets 生成 .env 内容，scp 到 `/opt/speakup/server/.env.production`（路径要对）。或者用 `ssh -o SetEnv=...` 显式透传。

## HTTPS

- 腾讯云网络层拦截了 443 端口的 TLS 流量（TCP 通、Client Hello 后无 Server Hello），所有 SSL 端口中只有 443 被阻断
- **当前方案**：Nginx 在 **8443** 端口提供 HTTPS，HTTP:80 自动 301 跳转到 `https://:8443`
- SSL 证书：Let's Encrypt，certbot 自动续期，同时覆盖新旧两个生产域名
- 老域名同样指向此服务器，同样走 8443
- 长期方案：ICP 备案后恢复 443 端口

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
cd web && pnpm run build                      # 前端构建（捕捉类型/import 错误）
# 有前端逻辑变更时：pnpm test run            # vitest

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

### 新增服务/路由时的 checklist

- [ ] 单元测试覆盖核心逻辑（mock 外部依赖）
- [ ] 集成测试覆盖 happy path + 边界（404、重复等）
- [ ] `docs/design/schema.md` 同步更新（如有新集合或字段变更）
- [ ] `docs/design/storage.md` 同步更新（如有新 OSS 路径）
- [ ] `CHANGELOG.md` 更新
- [ ] `pnpm run build` 通过（如有前端改动）

### 仓库工作流约定

1. **每次改动都开 PR**（不直接 push master）
2. **每个 PR 更 CHANGELOG.md**：`## [Unreleased]` 段，Keep a Changelog 分类
3. **测试要是代码**：不靠 curl 一次性脚本
4. **中文优先**：PR / commit / CHANGELOG / 文档 / 对话回复用中文，代码标识符和技术术语保持英文
