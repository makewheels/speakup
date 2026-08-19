# SpeakUp — AI 英语口语练习

看图片 → 说英语 → AI 看图给反馈。面向中国英语学习者的口语练习工具。

## 怎么用

1. 输入手机号登录（MVP，无验证码）
2. 系统给一张场景图片
3. 根据场景任务录一段英语，Qwen-ASR 转成文字
4. AI 根据任务和你的原话，判断是否办成、纠错并给出更地道的表达
5. 错点和好表达自动进错题本/笔记，间隔复习（中文提示回忆 + 词卡出题）

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | React 19 + Vite 8 |
| 后端 | FastAPI (Python 3.14) |
| 数据库 | MongoDB |
| 场景配图 | 火山方舟 Seedream 文生图（成本高，默认关闭），存阿里云 OSS |
| AI 反馈/出题 | DeepSeek 官方 `deepseek-v4-flash`（当前生产） |
| ASR / TTS | 百炼 `qwen3-asr-flash` / `qwen3-tts-flash` |
| 部署 | Docker Compose + Caddy，GitHub Actions 自动部署 |

## 本地开发

```bash
# 后端
cd server
uv sync
# 先按 infra 运维文档设置 INFISICAL_API_URL，并完成 infisical login
infisical run --env=dev --path=/ --recursive -- \
  uv run python main.py    # http://localhost:3001

# 前端
cd web
pnpm install
pnpm run dev               # http://localhost:5173
```

## 生产部署

push 到 master → GitHub Actions 自动部署到生产环境。

```bash
git push  # 自动触发部署
```

生产部署使用 GitHub OIDC 按需读取 Infisical；GitHub Actions 不保存业务密码。

## 环境变量

服务端通过 `APP_ENV` 区分环境。真实值由 Infisical 注入，变量说明模板见 `server/.env.example`。

| 变量 | 说明 |
|------|------|
| CHAT_API_KEY | 文字 LLM 密钥（生产为阿里云百炼） |
| VOICE_API_KEY | ASR/TTS 密钥（生产为百炼） |
| MONGO_URI | 本地 localhost / 生产内网地址 |
| PORT | API 端口，默认 3001 |
| APP_ENV | development / production |

## 项目结构

```
speakup/
├── web/                  # React 前端
│   └── src/pages/        # Login, Practice, Feedback, Review, History, SessionDetail, Profile, Share
├── server/               # FastAPI 后端
│   ├── main.py           # 入口
│   ├── services/         # 派题 / AI 评估 / ASR / TTS / 文生图 / OSS 等
│   ├── routes/           # auth, scenarios, correct, practice_sessions, review_items, feedbacks, transcribe, tts
│   ├── evals/            # corrector 端到端评测集（跑法见 server/evals/README.md）
│   └── tests/            # 单元 + 集成测试（分层见 CONTRIBUTING）
├── docs/                 # 文档（导航见 docs/README.md）
├── design/               # UI 设计稿画布（原型演示，非运行代码）
├── .github/workflows/    # CI/CD（ci-cd.yml 部署、evals.yml 评测）
└── scripts/              # 部署脚本
```

## 想贡献 / 改 bug

见 [CONTRIBUTING.md](CONTRIBUTING.md)（开发流程、测试分层、CHANGELOG 格式）；文档导航与架构图见 [docs/README.md](docs/README.md)；AI agent 的项目硬上下文（敏感信息 / 部署 / SSH）见 [AGENTS.md](AGENTS.md)。
