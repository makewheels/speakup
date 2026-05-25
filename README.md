# SpeakUp — AI 英语口语练习

看图片 → 说英语 → AI 看图给反馈。面向中国英语学习者的口语练习工具。

**地址：[https://speakup.a4.fit](https://speakup.a4.fit)**

## 怎么用

1. 输入手机号登录（MVP，无验证码）
2. 系统给一张场景图片
3. 看着图片用英语描述（Chrome 浏览器语音识别）
4. AI（VLM）看图 + 听你描述，纠正语法/用词、补充你漏掉的细节、推荐更地道的表达
5. 收藏生词到生词本，间隔复习

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | React 19 + Vite 8 |
| 后端 | FastAPI (Python 3.14) |
| 数据库 | MongoDB |
| 图片来源 | loremflickr 按 topic 关键词 |
| AI 反馈 | DashScope qwen3-vl-plus (VLM) |
| 部署 | Nginx + PM2, GitHub Actions 自动部署 |

## 本地开发

```bash
# 后端
cd server
cp .env.example .env       # 填入 DASHSCOPE_API_KEY
uv sync
uv run python main.py      # http://localhost:3001

# 前端
cd client
pnpm install
pnpm run dev               # http://localhost:5173
```

## 生产部署

push 到 master → GitHub Actions 自动部署到 101.42.94.17

```bash
git push  # 自动触发部署
```

## 环境变量

服务端通过 `.env.{APP_ENV}` 区分环境，不提交到 Git。模板见 `server/.env.example`。

| 变量 | 说明 |
|------|------|
| DASHSCOPE_API_KEY | 阿里云 DashScope |
| MONGO_URI | 本地 localhost / 生产内网地址 |
| PORT | API 端口，默认 3001 |
| APP_ENV | development / production |

## 项目结构

```
speakup/
├── client/               # React 前端
│   └── src/pages/        # Login, Practice, History, Vocabulary
├── server/               # FastAPI 后端
│   ├── main.py           # 入口
│   ├── services/         # 图片 URL 生成 + AI 纠正
│   └── routes/           # auth, generate, correct, sessions, vocabulary
├── .github/workflows/    # CI/CD
└── scripts/              # 部署脚本
```
