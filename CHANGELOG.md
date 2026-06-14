# Changelog

All notable changes to SpeakUp will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **雅思口语评分**：每次评估额外给一个 0~9（0.5 进制）的 IELTS band 分，反馈页 / 历史详情顶部大字号展示，存进 attempt。
- **CosyVoice 朗读**（替换浏览器内置 TTS）：新增 `POST /api/tts`，DashScope CosyVoice 合成英文朗读，按「模型+音色+文本」哈希缓存到 OSS（`tts/<sha1>.mp3`），同一句话第二次直接走缓存不再花钱；前端点击喇叭才请求合成。

### Changed
- **UI 全面英文化**：按钮 / 提示 / 标签 / 底部导航 / 登录页全改英文（Tap to start、Redo、Get feedback、Place/Scene/Goal、You said/Say this、Practice/Review/History/Me 等），学习内容里的中文「解释」保留中文；日期格式改 en-US。
- **反馈页视觉简化**：
  - 「我说的」去掉删除线、颜色加深（`--ink-3`→`--ink-2`），不再浅灰难辨
  - native 版按句换行展示，更清晰
  - 去掉 gap 分类徽章（语法/自然度…）和那行中文 summary（突兀）
  - 朗读按钮去掉「慢」、只留正常语速，喇叭图标放大（16→22）并加底色
- **练习页 URL 带 practiceId**：开始练习后地址栏变成 `/practice/<id>`，方便复制 id 排查 / 分享（内存已加载则不重复拉取）。
- 「我的」页移除过时的「语音识别 Chrome only」（现在全平台走后端 ASR）。

### Fixed
- **部署冷启动 502 / 偶发「语音识别失败」**（同一根因）：容器 `CMD` 用 `uv run`，每次冷启动都重新 `sync` 依赖 + 编译字节码（日志可见 `Downloading pygments` / `Bytecode compiled 3515 files`），启动慢 → 这段窗口 caddy 转发是 502。落在这窗口的 `/api/transcribe` 请求拿到 502，前端 `err.detail` 为空兜底成「ASR 失败」。修复：
  - Dockerfile：venv 进 PATH，`CMD` 直接 `uvicorn`（不再 runtime re-sync）
  - 新增 `GET /api/health`（不打 Mongo）+ compose `healthcheck`，`up -d --wait` 真正等到 app ready 才算部署完成
  - 前端 `transcribeAudio`：502/503 提示「服务正在重启，请稍后重试」，其余错误带上 HTTP 状态码 + 响应体片段；超时单独提示，不再吞成空文案
  - smoke check 改探 `/api/health`
- CI smoke check 静默失败：`curl ... | head` 管道没启用 pipefail，curl 拿 502/22 也算通过；改成不接管道、显式 `set -euo pipefail` + 6 次重试覆盖容器刚 up 时的 ready 窗口。
- 回滚 tag 错位：原逻辑先 `docker pull :latest`（已是新版）才 tag 成 `:previous`，导致 `:previous` 跟 `:latest` 永远指向同一个 image，`docker tag :previous :latest && compose up` 实际原地不动。改为基于"当前 running container 的 image ID"先打 `:previous` 再 pull 新 latest——抓的是真正在跑的那一版，不依赖 tag 状态。

### Changed
- **学习体验大改版（场景卡 / 反馈页 / 复习 / 历史 / 出题）**：
  - 场景卡：去掉所有 emoji（`要说` 的 🎯、地点里的 emoji，出题 prompt 也不再生成 emoji，旧数据渲染时剥离）；地点 / 场景 / 要说 三行统一字体、标签放大，只把「要说」加粗高亮作为唯一重点；去掉顶部「为你定制」标签
  - 反馈页：全页统一为「中文一种 + 英文一种」字体（新增 `--ff-en`，不再 serif/mono 混排）；差距点改成编号卡片 + 三行表格（我说的 / 应该说 / 为什么），原说法划掉、地道说法变色加粗可朗读；native 版变色加粗；每条差距加手动「加入复习」按钮
  - `why` 改为对照式解释（原说法哪里不好 + 地道说法为什么更好，≤40 字），不再只讲母语者怎么说
  - 复习页：首屏改为逐词卡片（正面=我当时说的，翻面=地道说法+朗读+「用这个词练一道题」），列表降为次要视图；地道说法 / 例句都可朗读
  - 错题进复习本：AI 自动 + 用户手动「加入复习」双通道
  - 历史页：按题目（scenarioId）分组，同一场景练多次折叠成一组、展开看每次；时间显示具体日期时间（不再「3 小时前」）
  - 出题：从「评估后触发」改为「取新题时按需补」——没练过的题低于阈值（3）才后台基于错题本补一道定制题
  - 朗读按钮从 🔊/🐢 emoji 换成小喇叭图标 + 「慢」文字
- **拆 caddy 为独立网关 `/opt/caddy/`**：以前 caddy 跟 speakup 绑同一个 compose、占住宿主 80/443，没法部署其他服务。改为：
  - `/opt/caddy/` 独立 compose + Caddyfile，唯一占用 80/443，由人工/单独仓库维护
  - speakup compose 不暴露宿主端口、只 expose 3001、加入 docker external network `edge`
  - workflow 不再 sync Caddyfile，DOMAIN 也不写进业务 .env（归 caddy 管）
  - smoke check 改打 `https://${DOMAIN}/api/...`
- 加新服务步骤：业务 compose 接 edge → Caddyfile 加 reverse_proxy → `caddy reload`

### Changed
- **镜像仓库回到 ACR + caddy 也搬到 ACR**：实测 ghcr.io 国内服务器拉取速度仅 24 KB/s（GFW 入境限速），caddy 公共 docker.io 国内已完全不通。改用阿里云 ACR 主账号固定密码登录（绕开 RAM 子用户临时 token 的 push 限制）；CI 每次部署同时把 `caddy:2-alpine` 从 docker.io 同步到 `b4/caddy`（首次推后续自动跳过）。docker-compose 两个镜像都走 ACR。

### Changed
- **镜像仓库 ACR → ghcr.io（已回退）**：阿里云 ACR 个人版 RAM 子用户临时 token 只能 pull 不能 push，要 push 必须控制台手动设固定密码。曾改用 GitHub Container Registry，但国内拉取速度无法接受，已回 ACR。

### Security
- 真实生产域名从代码仓库剥离：Caddyfile 用 `{$DOMAIN}` 占位，docker-compose 注入 `DOMAIN` 环境变量，CI 写 `.env` 时从 GitHub Secret `DOMAIN` 取值；AGENTS.md / docs/deploy.md 改占位描述

### Added
- **Docker 容器化部署**（PR #41）：Dockerfile 多阶段构建（pnpm 编前端→uv 后端）；docker-compose（speakup + Caddy 自动 HTTPS）；GitHub Actions push master → build → 推 ACR `b4/speakup`（`:latest`+`:previous` 回滚）→ SSH 部署 → smoke check
- 生产 FastAPI 直接托管前端静态文件（`APP_ENV=production` 时 mount `static/` 目录）
- RAM 子用户 `acr-ci` + speakup 专用策略（锁死 `b4/speakup` 仓库），凭据全部走 GitHub Secrets
- 部署交接文档：`docs/deploy.md`

### Removed
- `ecosystem.config.cjs`（PM2 配置，生产已下线）

### Changed
- **场景卡改表格式**：地点 / 场景 / 🎯 要说 三行，左标签列（浅底）+ 右内容列，行间分割线，格式更清晰；"要说"行高亮、要点字号加大到 19px
- **场景给出"要用英语说什么"的具体内容**（`points` 字段）：办事/讲解类给死内容（用户只管翻译表达，不用自己编剧情，如布置任务直接列出三件事），日常/描述/观点类给提示要点。评估也会对照 points 看是否表达到位。
- **练习页场景卡重新设计**：地点 / 场景 / 🎯 用英语说出这些 分行展示，"要说的内容"做大加粗成视觉重点（18px 列表）；去掉无用的"进入情境，开口完成任务"提示语
- `generate_scenarios.py` 改为题库文案的 source of truth：已存在的题重跑只就地更新文案，不重新生图、不花钱

### Added
- **场景广义化（实用 + 雅思口语范围）**：题库从清一色"办事投诉"扩到 5 类，每题带 `kind` + `title`：
  - `task` 办事交涉（咖啡给错单/预约看医生/申请加薪/给实习生布置任务/航班改签）
  - `chat` 日常问答（雅思 P1 / 街头采访：介绍家乡、聊手机习惯）
  - `describe` 描述长谈（雅思 P2 / vlog：难忘旅行、影响你的人、难忘礼物）
  - `opinion` 观点表达（雅思 P3 / 采访：远程办公、个人环保）
  - `explain` 讲解科普（讲讲春节为什么回家）
  - 共 13 题，随机派发不让用户选，难度 1~3 标记
- 历史列表显示场景标题（如"咖啡店给错咖啡"），不再只有 AI summary

### Changed
- **本地库 `speakup-dev` → `speakup`**：本地/生产是不同服务器，库名不必加 `-dev`（靠连接区分环境）；OSS 共用阿里云，仍用桶名 `speakup-dev`/`speakup-prod` 区分
- 清理无关数据库：删空的 `video_agent` / `video_agent_test`

### Fixed
- 重说改为最多 2 次（第 1 次 + 想练再来 1 次），去掉"第 N / 3 轮"硬性计数（让人误解成必须说满 3 次）；`MAX_ROUNDS` 3→2
- 历史不再展示"看了图没开口"的空记录（前端按 attempts 过滤），并清掉历史空数据；彻底的"开口才建记录"留待场景广义化 PR

### Changed (错题本改名 — 上线前，不迁移老数据)
- **集合 `vocabulary` → `reviewItems`**：错题不只是单词，更多是短语/句式，旧名体现不出"错题/复习项"；字段 `word` → `expression`
- 路由 `/api/vocabulary` → `/api/review-items`，前端页 `/vocabulary` → `/review`，VocabularyPage → ReviewPage，API 方法 `listReviewItems` 等同步
- 因材施教仍是这条链：大模型纠正出的点存进 `reviewItems` → 后台据此为该用户反向生成定制错题场景（`ownerUserId`）

### Changed (schema 重构 — 上线前清库重来，不迁移老数据)
- **集合 `sessions` → `practiceSessions`**：把 `sessions` 这个名字留给将来的登录会话；外键 `vocabulary.sessionId` → `practiceId`，路由 `/api/sessions` → `/api/practice-sessions`，前端 API 同步
- **删除 `files` 集合 + file_service + file_id**：AIGC 一图一题不需要 MD5 去重；图片元信息（模型/提示词）本就在 `scenarios` 里
- **图片不再把 URL 写死进库**：`scenarios` / `practiceSessions` 只存 `imageKey`，签名 URL 一律读取时现签（修正"ossImageUrl 直接存库"）；删掉 `imageFileId` / `ossImageUrl` / loremflickr `sourceUrl` 等随机图时代字段
- **OSS 路径资源为根**（参考 video-2022）：场景图 `scenarios/{id}/cover.jpg`，录音 `practiceSessions/{userId}/{yyyyMM}/{practiceId}/recording/{ts}.webm`
- **oss_storage 瘦身**：移除随机图时代的 `image_key` / `upload_from_url` / `sign_public_url`
- 文档同步：schema.md / storage.md / ids.md / scenario-mode.md / AGENTS.md

### Changed
- **模型升级并改走配置**：评估 qwen3.6-plus → qwen3.7-plus；生图 wanx-v1（异步轮询）→ wan2.7-image（multimodal-generation 同步接口，10~30s 出图，质量明显更好）；模型名与接口地址不再写死，env `CHAT_MODEL` / `IMAGE_MODEL` / `DASHSCOPE_BASE_URL` 可覆盖
- **设计文档补全**：新增 `docs/design/scenario-mode.md`（流程图/模型清单/出图策略/后台任务与删除策略总览）；schema.md 补 scenarios 集合与 sessions 新字段；storage.md 补录音路径与迁移计划；AGENTS.md 移除 loremflickr/VLM/部署等过时描述

### Removed
- 仓库二进制图片清除：`docs/architecture.png`（230KB，改为 docs/README.md 内 mermaid 图）、`web/src/assets/hero.png`（无任何引用的死文件）；约定图一律 mermaid 文本，不入库二进制

### Fixed
- CI 流水线移除 Deploy to production job：生产服务器已下线（重装挪作他用），每次合 master 都 SSH 连接拒绝导致流水线标红；将来重新部署时从 git 历史找回
- 反馈结果页加回场景图（之前评估完图片就消失，对照差距时看不到情境）
- 场景卡 / 反馈页整体字号调大（story/mission 15→17、native 17→19、差距点 14/16→16/18、说明文字 12/13→14/15 等）

### Added
- **场景任务模式（核心玩法重做）**：练习不再是"看图描述"，而是"场景 + 冲突 + 任务"——看图进入情境（如咖啡店做错单且赶飞机），开口用英语解决问题；AI 按"native 在这个场景会怎么说"评价
- **场景题库**：`scenarios` 集合全局共享、与用户解耦；`server/scripts/generate_scenarios.py` 预生成题目（手写场景文案 + 通义万相 wanx-v1 写实配图入 OSS），首批 3 题（咖啡店错单/深夜酒店查无预订/房东拖修暖气）；`GET /api/scenarios/next` 按"定制题 > 未练公共题 > 轮换"派题
- **三轮重说闭环**：同一场景最多说 3 轮；第 2 轮起 corrector 自动带上一轮 attempt 对比，返回 `progress {verdict: passed/improved/stuck, fixed[], remaining[], comment}`；前端过关大字、✅ 已用上 / ⏳ 还没用上 chips、重录时顶部提示条列出待用表达，3 轮强制"下一个场景"
- **因材施教定制题**：评估产生新复习项后，后台静默用错题本中最该复习的表达反向出题（Qwen 出场景 + 万相配图），生成只派给该用户的定制题（`ownerUserId` + `targetWords`），上限攒 2 道未练
- **地道说法发音**：`web/src/utils/tts.js`（浏览器 speechSynthesis），nativeVersion 和每个 gap better 旁 🔊 常速 / 🐢 0.75x 慢速
- **attempt 关联录音**：录音上传带 `attemptIndex`，回看历史可听每轮自己的原声；OSS 路径参考 video-2022 规范改为 `recordings/{userId}/{yyyyMM}/{sessionId}/{ts}.{ext}`

### Changed
- **corrector 改纯文本评估**：场景图是按文案生成的，评估时直接喂场景文案（地点/情境/任务/targetWords），不再下载图片转 base64，更快更省
- **session 快照场景**：创建会话存 scenario 快照（where/story/mission/targetWords）+ 题目图 fileId，题目日后修改不影响历史回看

### Removed
- 旧"随机图描述"模式整体下线：`routes/generate.py`、`services/image_generator.py`、loremflickr 依赖与图片归档后台任务

### Security
- 入库文件（README / AGENTS.md / CHANGELOG）中的真实生产域名全部移除，改为占位符——域名属于配置，与 IP/凭据同等对待不进代码

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
- 生产域名更换为与产品名对齐的新域名（具体值不入库）。Aliyun DNS / Nginx / TLS 证书已就位。HTTP 已通；HTTPS 受未备案影响在 TLS 握手层被中间件拦截，需后续 ICP 备案才能恢复。

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
