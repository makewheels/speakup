# SpeakUp — AI 英语口语练习应用

看图片 → 说英语 → AI (VLM) 看图给反馈。部署在 speakup.a4.fit (101.42.94.17)。

## 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | React 19 + Vite 8 | SPA, pnpm 管理 |
| 后端 | FastAPI + uv | Python 3.14, 异步 |
| 数据库 | MongoDB | 101.42.140.207:27017 |
| 图片来源 | loremflickr 随机图床 | 临时方案；按 topic 取关键词 |
| AI 反馈 | DashScope qwen3-vl-plus (VLM) | 看图 + 听描述 → JSON 反馈 |
| 部署 | PM2 + Nginx | ubuntu@101.42.94.17 |
| CI/CD | GitHub Actions | push → 自动部署 |

## 项目结构

```
speakup/
├── client/                    # React 前端 (pnpm)
│   └── src/
│       ├── api/client.js            # fetch 封装
│       ├── context/UserContext.jsx   # 登录状态 (localStorage)
│       ├── pages/                    # Login, Practice, History, Vocabulary
│       └── components/layout/        # 底部导航
├── server/                    # FastAPI 后端 (uv)
│   ├── main.py                      # 入口, lifespan 初始化
│   ├── config.py                    # 按 APP_ENV 加载 .env
│   ├── db/connection.py             # Motor async MongoDB
│   ├── services/
│   │   ├── image_generator.py       # 按 topic 拼 loremflickr URL
│   │   └── corrector.py             # qwen3-vl-plus 看图给反馈
│   └── routes/                      # auth, generate, correct, sessions, vocabulary
├── scripts/                   # 部署辅助脚本
├── .github/workflows/deploy.yml
└── ecosystem.config.cjs       # PM2 配置
```

## 环境隔离

| 环境 | MongoDB | 启动 |
|------|---------|------|
| dev (本地) | localhost/speakup-dev | `uv run python main.py` |
| prod | 101.42.140.207/speakup | PM2 管理 |

环境由 `APP_ENV` 切换（dev/prod 默认 development）。`config.py` 会加载 `.env.{APP_ENV}` 然后用 `.env` 兜底。

敏感信息不存代码：`.env*` 在 .gitignore，生产密码在 GitHub Secrets。参考 `server/.env.example`。

## 已知不足（待迭代）

- 登录：手机号直接注册无验证，无 token（MVP 自用阶段）
- 图片：loremflickr 随机给图，场景不可控；之前文档里提到的"通义万相生图 + 图片池"还没接回来
- 鉴权：`vocabulary` / `sessions` 的部分接口不校验 userId
- 模型名 `qwen3.6-plus` 待与 DashScope 实际可用模型对齐

## 启动

```bash
# 本地开发
cd server && uv run python main.py     # API :3001
cd client && pnpm run dev              # 前端 :5173 → proxy /api

# 生产部署 (自动)
git push  # GitHub Actions → rsync → PM2 reload

# 生产手动
ssh ubuntu@101.42.94.17
cd /opt/speakup/server && nohup .venv/bin/python main.py &
```

## 注意事项

- 语音识别仅 Chrome (Web Speech API)
- .env 文件不在版本控制中, rsync 时排除
- HTTPS 需要腾讯云安全组开放 443
- pnpm 全局 store: ~/Library/pnpm/store/v10
- uv 全局 cache: ~/.cache/uv
