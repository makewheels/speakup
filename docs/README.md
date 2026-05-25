# SpeakUp 代码架构

## 系统架构图

![架构图](architecture.png)

## 模块依赖关系

```mermaid
graph TB
    subgraph "Web 前端 (React 19)"
        main.jsx --> App.jsx
        App.jsx --> UserContext
        App.jsx --> Layout
        App.jsx --> LoginPage
        App.jsx --> PracticePage
        App.jsx --> VocabularyPage
        App.jsx --> ProfilePage
        PracticePage --> api/client.js
        VocabularyPage --> api/client.js
        Layout --> api/client.js
        LoginPage --> UserContext
        PracticePage --> UserContext
        Layout --> UserContext
        UserContext --> api/client.js
    end

    subgraph "Server 后端 (FastAPI)"
        main.py --> routes/auth
        main.py --> routes/generate
        main.py --> routes/correct
        main.py --> routes/sessions
        main.py --> routes/vocabulary
        main.py --> db/connection

        routes/correct --> services/corrector
        routes/generate --> services/image_generator
        routes/auth --> db/connection
        routes/correct --> db/connection
        routes/sessions --> db/connection
        routes/vocabulary --> db/connection

        services/corrector -.-> config.py
        services/oss_storage -.-> config.py
        db/connection -.-> config.py
    end

    subgraph "外部服务"
        services/corrector --> DashScope[DashScope qwen3.6-plus]
        services/image_generator --> loremflickr
        services/oss_storage --> AliyunOSS[Alibaba OSS]
        db/connection --> MongoDB
    end

    api/client.js ==>|fetch /api/*| main.py
```

## API 端点

| 路由 | 方法 | 说明 | 依赖 |
|------|------|------|------|
| `/api/auth/login` | POST | 手机号登录/注册 | MongoDB |
| `/api/generate` | POST | 生成练习图片 | loremflickr |
| `/api/correct` | POST | AI 评估口语 | DashScope VLM + MongoDB |
| `/api/sessions` | GET/POST | 练习记录 CRUD | MongoDB |
| `/api/vocabulary` | GET/POST/PUT/DELETE | 生词本 + 间隔重复 | MongoDB |

## 数据流

```
用户打开页面 → HTTPS:8443 → Nginx → 静态文件(React SPA)
     ↓
用户登录 → /api/auth/login → MongoDB(users)
     ↓
开始练习 → /api/generate → loremflickr 随机图片
     ↓
看图说英语 → Chrome SpeechRecognition → 文本
     ↓
提交评估 → /api/correct → DashScope qwen3.6-plus(看图+听文本)
     ↓                          ↓
     ↓                   返回: summary + nativeVersion + gaps[]
     ↓
保存到 sessions.attempts[] (MongoDB)
     ↓
用户收藏生词 → /api/vocabulary → 间隔重复复习
```
