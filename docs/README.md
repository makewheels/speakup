# SpeakUp 代码架构

图一律用 mermaid 文本画，不放二进制图片。业务流程详见 [design/scenario-mode.md](design/scenario-mode.md)。

## 系统架构图

```mermaid
graph TB
    User[用户 · Chrome] -->|HTTPS| Web

    subgraph "Web 前端 (React 19 + Vite, :5173)"
        Web[App Router + UserContext] --> Pages[Login / Practice / Vocabulary / History / SessionDetail / Profile]
        Pages --> Client[api/client.js<br/>fetch + SSE]
        Pages --> TTS[utils/tts.js<br/>后端 TTS + Audio 播放]
        Pages --> SR[MediaRecorder 录音<br/>后端 ASR 转写]
    end

    Client ==>|/api/*| API

    subgraph "Server 后端 (FastAPI, :3001)"
        API[main.py] --> R[routes: auth / scenarios / correct / transcribe / tts / sessions / vocabulary]
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
| `/api/sessions` | GET/POST | 创建会话（存场景快照）/ 历史列表 | MongoDB |
| `/api/sessions/{id}/recording` | POST | 上传录音，关联本轮 attempt | OSS |
| `/api/correct` `/api/correct/stream` | POST | AI 评估（流式 SSE），错点自动进复习 | 百炼文本模型 + MongoDB |
| `/api/transcribe` | POST | 录音转写 | 百炼 Qwen ASR |
| `/api/tts` | POST | 文本转自然语音并缓存到 OSS | 百炼 Qwen TTS + OSS |
| `/api/vocabulary` | GET/POST/PUT/DELETE | 错题本 + SM-2 间隔重复 | MongoDB |

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
    S-->>W: SSE 流式返回，错点入 vocabulary
    W->>S: 录音传 OSS（异步）
    S->>S: 后台：弱点表达反向生成定制题
    U->>W: 再说一遍（不封顶）或下一个场景
```
