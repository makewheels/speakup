# SpeakUp — AI 英语口语练习

看图片 → 说英语 → AI 纠正。面向中国英语学习者的口语练习工具。

**地址：[https://speakup.example.com](https://speakup.example.com)**

## 怎么用

1. 输入手机号登录
2. 系统自动生成一张场景图片
3. 看着图片用英语描述（Chrome 浏览器语音识别）
4. AI 纠正语法、用词、表达，五维评分
5. 收藏生词到生词本，间隔复习

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | React 19 + Vite 8 |
| 后端 | FastAPI (Python 3.14) |
| 数据库 | MongoDB |
| 图片生成 | 通义万相 wanx-v1 |
| 文本纠正 | Qwen3-Max |
| 图片加速 | 服务端全局图片池（预生成 10 张） |
| 部署 | Nginx + PM2, GitHub Actions 自动部署 |

## 本地开发

```bash
# 后端
cd server
cp .env.development .env   # 填入 DASHSCOPE_API_KEY
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

服务端通过 `.env.{NODE_ENV}` 区分环境，不提交到 Git。

| 变量 | 本地 | 生产 |
|------|------|------|
| MONGO_URI | localhost | 内网 MongoDB |
| DASHSCOPE_API_KEY | 开发 Key | 生产 Key |

## 项目结构

```
speakup/
├── client/               # React 前端
│   └── src/pages/        # Login, Practice, History, Vocabulary
├── server/               # FastAPI 后端
│   ├── main.py           # 入口
│   ├── services/         # 图片生成池 + AI 纠正
│   └── routes/           # auth, generate, correct, sessions, vocabulary
├── .github/workflows/    # CI/CD
└── scripts/              # 部署脚本
```
