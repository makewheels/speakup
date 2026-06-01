# Changelog

All notable changes to SpeakUp will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **复习页「原图重练」**：复习卡片点击进入 `/practice/:sessionId`，对当初那张原图重新描述一遍（复用练习流程）；旧数据无 `sessionId` 的词条不可点
- **复习接口关联场景图**：`GET /api/vocabulary` 用复习项的 `sessionId` 回查 session，返回签名后的 OSS 场景图（`sceneImageUrl` / `sceneFallbackUrl` / `topic`），供复习卡展示
- **OSS 签名工具** `sign_public_url`：把私有桶无签名公网链转成 1 小时签名 URL

### Changed
- **复习页改「左图右文」卡片**：96px 场景缩略图在左，右侧"你说的 → 地道版 + why"对比，底部"原图重练"入口 + 状态胶囊，删除按钮收到右侧独立窄列
- **历史页标题改用 AI summary**：每条历史以 AI 评估的一句话 summary 作标题（serif 字体），topic 关键词降级为小标签；无评估的 session 显示"未评估 · 看了图没开口"
- **UI 清晰度全面提升**：反馈页 gap 对比卡片左侧"你说的"改为橙红色（--warn），右侧"更地道"改为蓝色（--accent），错/对一眼可辨；历史详情页 gap 行颜色同步统一；复习页词汇卡片补上缩略图尺寸样式和删除按钮悬停色；`.su-corr` 从/到颜色与反馈页保持一致
- **corrector.py 迁移至 LangChain**：`correct_text` 改用 `ChatOpenAI.with_structured_output(CorrectResult)` 强制模型输出符合 Pydantic schema 的 JSON，彻底消除手工 JSON 解析失败风险；`correct_text_stream` 改用 `astream()` 流式收 token，末尾用 Pydantic 验证；新增 `GapItem` / `CorrectResult` Pydantic 模型作为输出 schema

### Added
- **录音上传 OSS**：练习时 MediaRecorder 与 Web Speech API 并行录音，AI 评估完成后自动上传到 OSS（`recordings/{userId}/{sessionId}/{ts}.webm`），失败静默忽略
- **历史页录音回放**：会话详情页每次尝试下方展示原生 `<audio>` 播放器，有录音才显示
- **后端录音端点**：`POST /api/sessions/{id}/recording` 接收音频 Blob，校验用户归属后上传 OSS

### Fixed
- **AI 错误消息区分超时 vs 其他错误**：之前任何异常都显示 "timed out"，现在区分超时（Timeout 类异常）和其他错误（如 DashScope 400）给出不同提示

### Changed
- **图片传给 DashScope 改用 OSS URL 直传**：评估时优先用 `session.ossImageUrl`（稳定内容），OSS URL 直接传给 DashScope 不再下载转 base64，省服务器出口带宽；loremflickr URL 仍走下载路径（内容每次随机）

### Security
- **入库文件不再包含任何 IP / 主机名 / 凭据**。`CLAUDE.md`、`README.md` 改用占位描述。
- 新增 [AGENTS.md](AGENTS.md) 作为面向所有 agent 的项目文档（遵循 agents.md 约定）。包含技术栈、项目结构、部署目标抽象描述、SSH 命令模板（具体 host 用 `<HOST>` 占位）、known deploy bugs、凭据旋转 checklist、仓库工作流约定。
- `CLAUDE.md` 改为 symlink → `AGENTS.md`，Claude Code 仍能读到。两份文档合一。
- `.gitignore` 加 `.claude/settings.local.json`（Claude Code 本地权限缓存，含历史 SSH 命令明文 IP，不应入库）。
- **遗留风险**：git history 里仍有 ~54 处旧 IP 引用（10 个历史 commit）+ 已关闭的 PR description / commit 里也含 IP。要彻底清除需 `git filter-repo` 重写历史（高风险：改写所有 commit SHA，破坏现有 clone / fork，需强制推送），等待用户授权。
- **建议旋转的凭据**：MongoDB 密码（在 AI 对话历史里出现过明文）。详见 [AGENTS.md 凭据旋转 checklist](AGENTS.md)。

### Fixed
- **结果页图片太小**：反馈页图片从 64×64 缩略图改为全宽正方形展示（复用 `.su-img`），与练习时看的图保持一致，topic 显示为左下角标签

### Added
- **prompt 强化口语化方向**：明确要求 better / example 给"咖啡馆英语"而非教科书答案，禁止学术/书面词汇（如用 "wiped out" 不用 "fatigued"，用 "It's freezing" 不用 "extremely cold"）
- **gap 新增 example 字段**：每个差距点 AI 给出一句自然例句，展示 better 表达在真实对话中的用法，前端反馈页和历史详情页同步展示
- **prompt 优化**：强制 better 只返回一个最佳表达（不再用 / 分隔多个备选）；强化中文输出要求（summary / why 必须中文）

### Fixed
- **SSE 流式评估报"AI service timed out"**：DashScope 流结束时会发一个 `choices=[]` 的 usage chunk，直接访问 `chunk.choices[0]` 触发 IndexError，被 except 吞掉误报超时。加 `if not chunk.choices: continue` 跳过即可。同时给 except 加了错误日志，方便排查未来的真实异常

### Added
- **file_service 测试**：新增 `tests/unit/test_file_service.py`（上传新图、MD5 去重跳过、OSS key 格式、mime 类型扩展名）和 `tests/unit/test_id_generator.py`（前缀、唯一性、时间戳格式、长度）
- **AGENTS.md 开发测试流程**：补充测试分层规范、每次改动 checklist、async 单元测试注意事项
- **files 集合 + ID 前缀体系**：新增 `files` MongoDB 集合统一管理图片/视频文件；ID 改为 `{prefix}_{毫秒时间戳}{6位随机hex}` 格式（`u_` / `s_` / `f_` / `w_`），参考 video-2022 规范；OSS 路径改为 `files/{fileId}/orig.jpg`，预留 `thumb` / `512` 等变体位置
- **MD5 内容去重**：图片上传前算 MD5 查 files 集合，相同内容只存一份 OSS，不重复上传
- **设计文档**：新增 `docs/design/ids.md`、`docs/design/storage.md`、`docs/design/schema.md`
- **历史列表页**：`/history` 展示所有练习记录，每条显示图片缩略图、topic、时间、AI summary 摘要、差距数；支持分页加载更多
- **会话详情页**：`/history/:sessionId` 展示单次会话的全部尝试，包括原文、改写、逐条差距分析
- **底部导航新增"历史"标签**：使用 clock 图标，路由到 `/history`
- **复习列表图片缩略图**：vocabulary 列表每行左侧显示对应练习图片（使用 `imageUrl` 字段）
- **SSE 流式输出**：`POST /api/correct/stream` 用 Server-Sent Events 实时推送 AI token，前端评估阶段实时显示"已生成 N 字符"进度，体感等待明显缩短
- **AI 自动决定复习项**：prompt schema 新增 `saveToReview` 字段，AI 对每个 gap 判断是否值得记忆，后端自动写入 vocabulary，响应带 `autoSaved` 计数
- **图片归档到 OSS**：创建 session 时后台任务（BackgroundTask）把 loremflickr 图片拉到阿里云 OSS，key 格式 `images/{userId}/{sessionId}.jpg`，更新 `session.ossImageUrl`
- **OSS 路径规范**：`oss_storage.py` 新增 `image_key(user_id, session_id)`、`upload_from_url(key, url)` 异步函数、`upload_bytes_async` 线程池包装；bucket 本身区分 dev/prod，key 内不重复存环境信息

### Changed
- **反馈页移除手动"添加到复习"按钮**：AI 已自动收录标注项，gap 卡片上显示"已收录"标签；section-title 显示自动保存数量

### Fixed
- **AI 评估卡住问题**：关闭 qwen3 thinking 模式（`enable_thinking: false`），避免模型先生成大量隐藏思考 token 导致响应极慢
- **后端 API 超时**：DashScope 调用增加 60 秒超时，超时后返回友好提示而非无限等待
- **前端请求超时**：所有 fetch 请求增加 90 秒 AbortController 超时，超时后提示用户重试
- **防御 `<think>` 标签**：解析 AI 响应时剥离可能混入的 thinking 标签，避免 JSON 解析失败
- **CI Node.js 20 弃用警告**：升级 `actions/checkout` v4→v5、`setup-node` v4→v5、`setup-uv` v6→v7
- **麦克风 HTTP 拦截**：HTTP 下 Chrome 静默拒绝麦克风权限且不弹窗，增加协议检测和明确提示
- **HTTPS 恢复**：腾讯云 443 端口 TLS 被网络层拦截，改用 8443 端口提供 HTTPS；HTTP 自动 301 跳转到 `https://:8443`
- **部署目录缺失**：rsync 推送 `web/dist` 前未创建目标目录导致部署失败，改为 rsync 前先 mkdir + client→web 迁移

### Changed
- **AI 反馈改中文**：summary 和 gap.why 改用中文输出，original/better/nativeVersion 保持英文
- **纠正区字体放大**：from/to 13px→15px、reason 12px→14px、arrow 11px→13px、category 10px→11px
- **前端文件夹重命名**：`client/` → `web/`，CI/CD 和部署路径同步更新

### Security
- **入库文件不再包含任何 IP / 主机名 / 凭据**。`CLAUDE.md`、`README.md` 改用占位描述。
- 新增 [AGENTS.md](AGENTS.md) 作为面向所有 agent 的项目文档（遵循 agents.md 约定）。包含技术栈、项目结构、部署目标抽象描述、SSH 命令模板（具体 host 用 `<HOST>` 占位）、known deploy bugs、凭据旋转 checklist、仓库工作流约定。
- `CLAUDE.md` 改为 symlink → `AGENTS.md`，Claude Code 仍能读到。两份文档合一。
- `.gitignore` 加 `.claude/settings.local.json`（Claude Code 本地权限缓存，含历史 SSH 命令明文 IP，不应入库）。
- **遗留风险**：git history 里仍有 ~54 处旧 IP 引用（10 个历史 commit）+ 已关闭的 PR description / commit 里也含 IP。要彻底清除需 `git filter-repo` 重写历史（高风险：改写所有 commit SHA，破坏现有 clone / fork，需强制推送），等待用户授权。
- **建议旋转的凭据**：MongoDB 密码（在 AI 对话历史里出现过明文）。详见 [AGENTS.md 凭据旋转 checklist](AGENTS.md)。

### Added
- **阿里云 OSS 集成**：创建 dev/prod bucket（speakup-dev, speakup-prod），RAM 用户 speakup-oss + 仅限 speakup bucket 的 IAM 策略，oss2 SDK 服务模块 `oss_storage.py`
- **前端 vitest 测试**：`client/src/**/*.test.jsx`，11 个用例覆盖 Icon 渲染 + LoginPage 表单校验 / 提交，807ms 跑完。CI 在 `test-client` job 里跑。
- **差距框架（gap-exposure）** 取代"纠错"作为产品本质 — see `SPEC.md` §2
- 新 AI 输出 schema：`{summary, nativeVersion, gaps[{original, better, why, category}]}`
- 视觉系统从 Claude Design 移植：Newsreader 衬线 + Geist + JetBrains Mono + 暖纸色，全套 design tokens
- 个人中心页 `/me`（含退出登录）
- 复习页 filter tabs（全部 / 待复习 / 已掌握）
- AI 评估等待 UX：elapsed counter + 按时间段轮转 hint
- `server/tests/`：pytest 单元 + 集成测试，**DashScope 调用全部 mock**，零 API 花费
- conftest cost-guard fixture：拒绝任何测试期间的真实 DashScope 调用
- GitHub Actions CI/CD：test + client build 通过后才执行 deploy
- `CHANGELOG.md`（本文件）

### Changed
- 生产域名 `speakup.example.com` → `speakup.example.com`，对齐产品名。Aliyun DNS / Nginx / TLS 证书已就位。HTTP 已通；HTTPS 受未备案影响在 TLS 握手层被中间件拦截，需后续 ICP 备案才能恢复。

### Fixed
- 部署流水线 rsync 不再把本地 `.venv` 推到远端（之前会用本地 macOS Python 路径覆盖远端 Linux venv，导致 PM2 启动失败 502）。`.venv` 加进 `--exclude` 列表。
- 原"生词本/错题本"统一改名为 **复习**（review item），UI / 数据语义对齐
- 环境变量 `NODE_ENV` → `APP_ENV`（Python 项目不该用 Node 命名）
- 图片尺寸：loremflickr 1024×1024 → 640×640，加快 DashScope 看图
- 底部导航：3 tab（练习 / 复习 / 我的）
- AI prompt 完全重写：写明"暴露差距 / 不脑补 /不改 idea / 不炫词 / 不元话语"五条原则
- **AI 评估提速**：服务端先把图片 fetch 下来转 base64 data URL 再传给 DashScope，避免 DashScope 自己二次拉 loremflickr（国内访问海外图床慢）。失败自动 fallback 回原 URL，不会让 AI 调用挂掉。预计省 30-60s。
- conftest 加 `_no_image_fetch` 文件级 fixture 在 corrector 单测里 mock 掉网络调用，CI 不依赖外部网络

### Fixed
- `sessions.createdAt` 之前从未写入，导致历史列表排序乱、日期显示 Invalid Date
- `vocabulary` 路由的 review / delete 现在强制校验 userId，跨用户改写返回 404
- 复习项字段语义对位：`original` / `word` / `note` / `contextSentence`（原 `chinese` 实际存的是英文语法解释，已废弃）
- 模型名修正为 `qwen3.6-plus`

### Removed
- 旧 Node.js 备份目录 `server-nodejs-backup/`（1500+ 行未使用）
- 死代码：`HomePage`（无路由 + 调用了不存在的 API）、`HistoryPage`（被复习页吸收）
- `image_generator.py` 里空函数 `init_pool` / `start_prefetch`
- 过时 `SCENE_PROMPTS` 字典（切到 loremflickr 后再也没用过）
- 五维评分、主题选择等被砍功能的 CSS 残留
