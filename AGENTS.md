# SpeakUp — AI 英语口语练习应用

看图片 → 说英语 → AI (VLM) 看图给反馈。生产域名 `speakup.example.com`。

> 本文件遵循 [AGENTS.md](https://agents.md) 约定，是面向所有 AI agent（Claude Code / Cursor / 其他）的项目说明。`CLAUDE.md` symlink 到这里。

## 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | React 19 + Vite 8 | SPA, pnpm 管理 |
| 后端 | FastAPI + uv | Python 3.14, 异步 |
| 数据库 | MongoDB | 腾讯 Lighthouse 独立实例（内网直连）|
| 图片来源 | loremflickr 随机图床 | 临时方案；按 topic 取关键词 |
| AI 反馈 | DashScope qwen3-vl-plus (VLM) | 看图 + 听描述 → JSON 反馈 |
| 部署 | PM2 + Nginx | 腾讯 Lighthouse |
| CI/CD | GitHub Actions | push → 自动部署 |

## 项目结构

```
speakup/
├── client/                    # React 前端 (pnpm)
│   └── src/
│       ├── api/client.js            # fetch 封装
│       ├── context/UserContext.jsx   # 登录状态 (localStorage)
│       ├── pages/                    # Login, Practice, Vocabulary, Profile
│       └── components/layout/        # 底部导航
├── server/                    # FastAPI 后端 (uv)
│   ├── main.py                      # 入口, lifespan 初始化
│   ├── config.py                    # 按 APP_ENV 加载 .env
│   ├── db/connection.py             # Motor async MongoDB
│   ├── services/
│   │   ├── image_generator.py       # 按 topic 拼 loremflickr URL
│   │   └── corrector.py             # qwen3-vl-plus 看图给反馈
│   ├── routes/                      # auth, generate, correct, sessions, vocabulary
│   └── tests/                       # pytest, unit + integration
├── scripts/                   # 部署辅助脚本
├── .github/workflows/ci-cd.yml
└── ecosystem.config.cjs       # PM2 配置
```

## 环境隔离

| 环境 | MongoDB | 启动 |
|------|---------|------|
| dev (本地) | localhost/speakup-dev | `uv run python main.py` |
| prod | 内网 IP / speakup | PM2 管理 |

环境由 `APP_ENV` 切换（dev/prod 默认 development）。`config.py` 加载 `.env.{APP_ENV}` 然后用 `.env` 兜底。

## 启动

```bash
# 本地开发
cd server && uv run python main.py     # API :3001
cd client && pnpm run dev              # 前端 :5173 → proxy /api

# 生产部署 (自动)
git push  # GitHub Actions → rsync → PM2 reload
```

## 注意事项

- 语音识别仅 Chrome (Web Speech API)
- `.env` 文件不在版本控制中, rsync 时排除
- pnpm 全局 store: `~/Library/pnpm/store/v10`
- uv 全局 cache: `~/.cache/uv`

## 已知不足（待迭代）

- 登录：手机号直接注册无验证，无 token（MVP 自用阶段）
- 图片：loremflickr 随机给图，场景不可控；通义万相生图 + COS 池待接
- 模型名 `qwen3.6-plus` 待与 DashScope 实际可用模型对齐
- 部署系统有 secrets 不透传 + 路径错位 bug，详见下文 "部署 known issues"
- HTTPS 当前被中间件拦截（疑似未备案），需 ICP 备案才能恢复

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
aliyun alidns DescribeDomainRecords --DomainName a4.fit

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

- `speakup.example.com` 的 TLS 握手在外部访问时被中间件切（TCP 通、Client Hello 后无 Server Hello）
- 怀疑是未备案导致的运营商/中间件拦截
- 临时方案：HTTP 直供；certbot --redirect 加的 301 已手动关掉
- 老域名 `speakup.example.com` 同样问题，保留服务作为兼容
- 长期方案：ICP 备案

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

## 仓库工作流约定

详细规则在 agent memory，简述：

1. **每次改动都开 PR**（不 push master）：`git checkout -b <type>/<slug>` → 改 → `gh pr create`
2. **每个 PR 更 CHANGELOG.md**：`## [Unreleased]` 段，用 Keep a Changelog 分类（Added / Changed / Fixed / Removed / Security）
3. **测试要是代码**：后端 `server/tests/`（pytest），前端 `client/src/**/*.test.jsx`（vitest），不靠 curl 一次性脚本
4. **测试不调用大模型**：conftest 有 cost guard fixture 拒绝真实 DashScope 调用；新测试必须 mock 掉
5. **报告"完成"前必须本机跑过对应测试**：build / pytest / vitest 全过，且功能路径手动或自动验过一遍
6. **中文优先**：PR / commit / CHANGELOG / 文档 / 对话回复用中文。代码标识符和技术术语保持英文。
