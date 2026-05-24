# SpeakUp — AI 英语口语练习应用

## 项目概述

一款面向中国英语学习者的 Web 口语练习应用。用户看图片 → 说英语 → AI 纠正语法/用词/表达。

## 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| 前端 | React 19 + Vite 8 | SPA, react-router-dom 路由 |
| 后端 | Express 5 + Node.js | REST API, ES modules |
| 数据库 | MongoDB 8 + Mongoose 9 | 文档型存储 |
| 图片生成 | 通义万相 wanx-v1 | DashScope 异步 API, ~0.10 元/张 |
| 文本纠正 | Qwen3-Max | DashScope OpenAI-compatible API |
| 包管理 | pnpm | 全局 store (`~/Library/pnpm/store/v10`) |

## 项目结构

```
~/workspace/learning/speakup/
├── client/                  # React 前端
│   ├── src/
│   │   ├── api/client.js          # API 请求封装
│   │   ├── context/UserContext.jsx # 用户登录状态
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx       # 手机号登录
│   │   │   ├── PracticePage.jsx    # 核心练习页（图片+录音+纠正）
│   │   │   ├── HistoryPage.jsx     # 练习历史列表
│   │   │   └── VocabularyPage.jsx  # 生词本 + 间隔复习
│   │   ├── components/layout/Layout.jsx  # 底部导航
│   │   ├── App.jsx   # 路由配置
│   │   └── App.css   # 全局样式
│   └── vite.config.js  # 含 /api 代理到 3001
├── server/                  # Express 后端
│   ├── index.js             # 入口, MongoDB 连接 + 路由挂载
│   ├── db/
│   │   ├── connection.js    # Mongoose 连接
│   │   └── models/
│   │       ├── User.js           # 手机号 + 昵称
│   │       ├── Session.js        # 练习会话, 内嵌 attempts(纠正记录)
│   │       └── VocabularyItem.js # 生词, 含复习间隔字段
│   ├── services/
│   │   ├── imageGenerator.js     # 通义万相异步调用 + 内存缓存
│   │   └── corrector.js          # Qwen3-Max 纠正 + 五维评分
│   ├── routes/
│   │   ├── auth.js        # POST /api/auth/login
│   │   ├── generate.js    # POST /api/generate/next, /prefetch
│   │   ├── correct.js     # POST /api/correct
│   │   ├── sessions.js    # CRUD /api/sessions
│   │   └── vocabulary.js  # CRUD + review /api/vocabulary
│   └── .env               # DASHSCOPE_API_KEY, MONGO_URI
└── workspace/
    ├── learning/speakup/   ← 当前项目
    ├── tools/              ← reverse-http-tunnel, site_monitor, ticket-archiver
    └── media/              ← ai-podcast, easy-book, wechat-analyzer, public-notes, video-2022
```

## API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 手机号登录, 返回 userId, 触发图片 prefetch |
| POST | /api/generate/next | 获取下一张图(缓存优先), 自动 replenish |
| POST | /api/generate/prefetch | 后台预生成图片 |
| POST | /api/correct | 纠正文本, 返回五维评分 + 逐条修正 |
| POST | /api/sessions | 创建练习会话 |
| GET | /api/sessions?userId= | 用户会话列表(按时间倒序) |
| GET | /api/sessions/:id | 会话详情(含所有 attempts) |
| GET | /api/vocabulary?userId= | 生词列表, ?due=true 筛选待复习 |
| POST | /api/vocabulary | 批量添加生词 |
| POST | /api/vocabulary/:id/review | 复习生词(remembered: bool), 更新间隔 |

## 核心业务流程

```
用户登录 → 后台 prefetch 图片(异步)
  ↓
进入练习页 → /api/generate/next → 图片就绪
  ↓
用户录音 → Web Speech API 转文字
  ↓
提交纠正 → Qwen3-Max 返回:
  - correctedText: 完整纠正版
  - corrections[]: 逐条错误(原文/修正/中文原因)
  - tips[]: 学习建议
  - scores: { grammar, vocabulary, completeness, fluency, structure } 各 1-5
  ↓
用户可收藏到生词本 → 轻量间隔复习
  ↓
"再来一题" → 已 prefetch, 秒出图
```

## 图片缓存策略

- 内存 Map: `userId → { imageUrl, topic, prompt }`
- 登录时自动 prefetch
- 每次取走图片后立即后台 replenish
- 如果请求时 prefetch 还在进行中, await 等待
- 图片 URL 有效期内(约数小时), 无需 OSS

## 启动方式

```bash
# 1. 配置
cp server/.env.example server/.env
# 填入: DASHSCOPE_API_KEY=sk-xxx, MONGO_URI=mongodb://localhost:27017/speakup

# 2. 确保 MongoDB 运行中
mongosh --eval "db.version()"

# 3. 启动后端 (3001)
cd server && pnpm dev

# 4. 启动前端 (5173, 代理 /api → 3001)
cd client && pnpm run dev
```

## 注意事项

- 语音识别使用 Web Speech API, **仅在 Chrome 浏览器可用**
- 通义万相只支持异步模式 (wanx-v1), 生成一张图约 20-40 秒
- Qwen3-Max 的 JSON 输出偶尔被 markdown 包裹, corrector.js 做了 strip 处理
- pnpm 开启了 shamefully-hoist 以解决 Vite 依赖解析

## 待做事项

- [ ] 优化图片 prompt: 更精确的动作/物品/空间关系
- [ ] 支持音频录制保存 (MediaRecorder) + 回听
- [ ] 转录文本可编辑
- [ ] 部署到服务器
- [ ] 发音评分 (Whisper API)
- [ ] 中级/高级难度分层
