# SpeakUp 文档入口与代码架构

本文件是全部文档的导航入口。图一律用 mermaid 文本画，不放二进制图片。业务流程详见 [design/scenario-mode.md](design/scenario-mode.md)。

## 文档地图

按主题查找文档：

| 位置 | 内容 | 维护约定 |
|------|------|---------|
| `docs/业务/*.md` | **当前已实现**行为的分模块文档（错题本与复习、用户反馈等） | 每次行为变更必须同步更新 |
| `docs/design/schema.md` | MongoDB 集合字段（数据模型事实源） | 字段变更必须同步 |
| `docs/design/*.md` | 设计稿（含未实现的，文首标状态） | 落地后回写进展 |
| `docs/deploy.md` | 部署指南（架构 / 首次部署 / 回滚 / 运维命令） | 部署形态变化时同步 |
| `docs/evals.md` | 评测方法、评测方向与历次模型横评基线 | 跑完横评后回写 |
| `docs/langfuse.md` | Langfuse 自托管部署、埋点与踩坑记录 | 部署/埋点变化时同步 |
| `docs/scenario-evaluation.md` | 题目评测方案（8 维度 / 用户模拟器 / 发布门禁，设计稿） | — |
| `server/evals/README.md` | 评测集跑法 / 任务文件格式 / Langfuse 回写 | evals 代码变化时同步 |
| `design/README.md` | 根目录 `design/` 的 UI 设计稿画布原型 | — |
| `CHANGELOG.md` | 变更记录（北京时间倒序） | 每次改动必须追加 |
| `CONTRIBUTING.md` | 开发流程 / 测试分层 / CHANGELOG 格式（人 + agent 共用） | 流程变化时同步 |
| `AGENTS.md` | AI agent 入口：代码地图 / 敏感信息约定 / 部署运维 | 结构变化时同步 |

## 系统架构图

```mermaid
graph TB
    User[用户 · Chrome] -->|HTTPS| Web

    subgraph "Web 前端 (React 19 + Vite, :5173)"
        Web[App Router + UserContext] --> Pages[Login / Practice / Review / History / SessionDetail / Profile]
        Pages --> Client[api/client.js<br/>fetch + SSE]
        Pages --> TTS[utils/tts.js<br/>后端 TTS + Audio 播放]
        Pages --> SR[MediaRecorder 录音<br/>后端 ASR 转写]
    end

    Client ==>|/api/*| API

    subgraph "Server 后端 (FastAPI, :3001)"
        API[main.py] --> R[routes: auth / scenarios / correct / transcribe / tts / practice_sessions / review_items / feedbacks]
        R --> Corrector[services/corrector.py<br/>口语评估 + 三轮 progress]
        R --> Scen[services/scenario_service.py<br/>派题 + 定制题后台生成]
        Scen --> Wanx[services/wanx.py 文生图]
        R --> OSS[services/oss_storage.py]
        R --> DB[db/connection.py]
    end

    Corrector --> ChatModel[DeepSeek · deepseek-v4-flash]
    R --> Voice[阿里云百炼 · qwen3-asr-flash / qwen3-tts-flash]
    Wanx -.默认关闭.-> Seedream[火山方舟 · env IMAGE_MODEL]
    OSS --> Aliyun[阿里云 OSS 私有桶<br/>签名 URL 1h]
    DB --> Mongo[(MongoDB speakup-dev)]
```

## API 端点

| 路由 | 方法 | 说明 | 依赖 |
|------|------|------|------|
| `/api/auth/login` | POST | 手机号登录/注册 | MongoDB |
| `/api/scenarios/next` | GET | 派题：定制题 > 未练公共题 > 轮换 | MongoDB + OSS 签名 |
| `/api/scenarios/practice-word` | POST | 「用这个词练一题」即时出定制场景题 | 文本模型 + 文生图 |
| `/api/practice-sessions` | GET/POST | 创建会话（存场景快照）/ 历史列表；`/{pid}` 读单条 | MongoDB |
| `/api/practice-sessions/{pid}/recording` | POST | 上传录音，关联本轮 attempt | OSS |
| `/api/practice-sessions/{pid}/share` | POST/DELETE | 开启/取消分享（token 幂等复用） | MongoDB |
| `/api/share/{token}` | GET | 公开读取已分享的练习结果（无鉴权） | MongoDB + OSS 签名 |
| `/api/correct` `/api/correct/stream` | POST | AI 评估（流式 SSE），错点自动进错题本 | 文本模型 + MongoDB |
| `/api/correct/chat/stream` | POST | 针对本轮反馈的 coach 追问（SSE） | 文本模型 |
| `/api/transcribe` | POST | 录音转写 | 百炼 Qwen ASR |
| `/api/tts` | POST | 文本转自然语音并缓存到 OSS | 百炼 Qwen TTS + OSS |
| `/api/review-items` | GET/POST | 错题本（错题 mistake / 好表达笔记 note）；收纳/恢复/惰性翻译等子路由见 [业务/1-错题本与复习.md](业务/1-错题本与复习.md) | MongoDB（translate 另走文本模型） |
| `/api/feedbacks` | POST/GET | 用户反馈（练习结果点赞踩 + 全局反馈），带 AI 反馈快照 | MongoDB |
| `/api/health` | GET | 健康检查 | — |

## 数据流（一次练习）

```mermaid
sequenceDiagram
    participant U as 用户
    participant W as Web
    participant S as Server
    participant Q as DeepSeek / DashScope
    U->>W: 进入练习页
    W->>S: GET /scenarios/next → POST /sessions
    S-->>W: 场景（图 + 情境 + 任务）
    U->>W: 开口说（语音识别转文本 + 录音）
    W->>S: POST /correct/stream
    S->>Q: 场景文案 + 口述文本（第2轮起带上一轮）
    Q-->>S: summary / nativeVersion / standardAnswer / gaps / progress
    S-->>W: SSE 流式返回，错点入 reviewItems（错题本）
    W->>S: 录音传 OSS（异步）
    S->>S: 后台：弱点表达反向生成定制题
    U->>W: 再说一遍（不封顶）或下一个场景
```
