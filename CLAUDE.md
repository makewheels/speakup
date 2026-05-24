# SpeakUp — AI 英语口语练习应用

看图片 → 说英语 → AI 纠正。部署在 speak.a4.fit (101.42.94.17)。

## 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | React 19 + Vite 8 | SPA, pnpm 管理 |
| 后端 | FastAPI + uv | Python 3.14, 异步 |
| 数据库 | MongoDB | 101.42.140.207:27017 |
| 图片生成 | 通义万相 wanx-v1 | DashScope 异步 API |
| 文本纠正 | Qwen3-Max | DashScope OpenAI 兼容 |
| 部署 | PM2 + Nginx | ubuntu@101.42.94.17 |
| CI/CD | GitHub Actions | push → 自动部署 |

## 项目结构

```
speakup/
├── client/                    # React 前端 (pnpm)
│   └── src/
│       ├── api/client.js            # fetch 封装
│       ├── context/UserContext.jsx   # 登录状态
│       ├── pages/                    # Login, Practice, History, Vocabulary
│       └── components/layout/       # 底部导航
├── server/                    # FastAPI 后端 (uv)
│   ├── main.py                      # 入口, lifespan 初始化
│   ├── config.py                    # 按 NODE_ENV 加载 .env
│   ├── db/connection.py             # Motor async MongoDB
│   ├── services/
│   │   ├── image_generator.py       # 图片池 (10张预生成)
│   │   └── corrector.py             # Qwen3-Max 纠正
│   └── routes/                      # auth, generate, correct, sessions, vocabulary
├── server-nodejs-backup/      # 旧 Node.js 代码(已废弃)
├── scripts/                   # 部署辅助脚本
├── .github/workflows/deploy.yml
└── ecosystem.config.cjs       # PM2 配置
```

## 环境隔离

| 环境 | MongoDB | 图片 | 启动 |
|------|---------|------|------|
| dev (本地) | localhost/speakup-dev | DashScope 临时 URL | `uv run python main.py` |
| prod | 101.42.140.207/speakup | 图片池预生成 | PM2 管理 |

敏感信息不存代码：`.env*` 在 .gitignore，生产密码在 GitHub Secrets。

## 图片池机制

- 全局池 10 张图，低于 5 张自动补充
- 服务启动时自动填充 (init_pool)
- 用户请求秒取 (pool.pop)
- 后台异步补充，用户无感

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
- 通义万相仅异步模式, 生成一张约 20-40s
- .env 文件不在版本控制中, rsync 时排除
- HTTPS 需要腾讯云安全组开放 443
- pnpm 全局 store: ~/Library/pnpm/store/v10
- uv 全局 cache: ~/.cache/uv
