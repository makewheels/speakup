# Changelog

All notable changes to SpeakUp will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning follows [SemVer](https://semver.org/).

## [Unreleased]

> 时间戳精确到分钟（`YYYY-MM-DD HH:MM`，北京时间 UTC+8）。同一天多次改动按时间倒序——最新在最上。每段下面扁平列表，前缀标类型（`add` / `change` / `fix` / `test` / `chore`）。

### 2026-08-14 15:57

- **chore(evals)**：DeepSeek probe 验证完成（key 可用、`deepseek-v4-flash` 探活通过），移除临时 `deepseek-probe.yml`。

### 2026-08-14 15:25

- **change(model)**：生产文字评估从百炼 `qwen3.8-max` 切到 DeepSeek 官方 `deepseek-v4-flash`（当前版本 DeepSeek-V4-Flash-0731，2026-07-31 重新后训练）；旧名 `deepseek-chat` 已于 2026-07-24 退役，不再使用。
- **add(evals)**：新增临时 DeepSeek probe workflow（`deepseek-probe.yml`），用生产 key 手动验证模型列表/探活，验证完成后移除。
- **chore(cost)**：llm_audit 定价表补 `deepseek-v4-flash`（按官方 $0.14/$0.28 每百万 tokens 估算）。
- **fix(docs)**：架构/部署/场景/评测文档同步当前生产模型链路；regression 基线待在新模型上重跑重建。

### 2026-08-14 02:17

- **fix(media)**：场景没有图片/视频，或唯一媒体加载失败时，不再显示巨大空白方块，直接让用户看场景任务卡。
- **test**：覆盖无媒体、单图失败、无封面视频失败三种降级。

### 2026-08-14 02:06

- **fix(chat)**：追问对话在尚未输出任何 token 时遇到瞬时模型错误，自动重试一次；已经开始输出时不重试，避免重复回答。
- **test**：覆盖追问首 token 前重试成功、两次都失败和部分输出后不重试。

### 2026-08-14 01:51

- **fix(model)**：百炼服务恢复后，生产文字评估从临时 `deepseek-chat` 升级到新横评最佳的 `qwen3.8-max`，同步当前架构文档。
- **test(evals)**：初筛 6 个当前模型，再对前 3 名跑 regression 12 × 3 trials；`qwen3.8-max` 取得 pass@3 12/12、pass^3 10/12、平均延迟 3.1s。

### 2026-08-14 01:45

- **chore(deploy)**：为 CI/CD 增加手动触发入口，支持仅轮换 GitHub Secrets 时不改代码也能启动一次全新部署。

### 2026-08-14 01:30

- **fix(voice)**：云端 ASR 不可用时进入可编辑转写态，用户可手动输入后继续 AI 评估；云端 TTS 不可用时自动降级到浏览器英文朗读，同一页面会停止重复请求已确认不可用的后端。
- **change(ui)**：转写失败后的复核态改为可编辑文本框，不再用空文本和禁用按钮把用户卡死。
- **test**：覆盖 ASR 失败后的手动转写闭环和 TTS 浏览器降级、停止与缓存行为。

### 2026-08-14 01:20

- **add(data)**：用户首次创建时记录 `sourceType=human|ai_test`，练习、复习项、定制题及 LLM 审计记录同步冗余来源；历史缺字段按 `human` 兼容，生产统计可直接排除自动体验数据。
- **fix(data)**：产品/结果反馈继承同一来源，反馈导出默认排除自动体验；`ai_test` 账号取题时跳过后台补题，避免自动体验污染共享题库。
- **fix(docs)**：部署与架构文档同步当前生产模型链路：文字评估为 DeepSeek 官方 `deepseek-chat`，语音为百炼 Qwen ASR/TTS。
- **test**：覆盖 AI 测试用户来源不可被普通登录改写，以及练习、复习项的来源继承。

### 2026-08-13 00:52

- **add(evals)**：新增 `evals/compare.py` 跨模型对比 CLI——模型 spec 参数化（`name[@base_url[@KEY_ENV]]`，key 只走环境变量）、多 trial 按 pass@k/pass^k 判、HTML 矩阵报告 + JSON 存档、`--ping` 探活；harness 收敛 client 换单例逻辑为 `use_client` 上下文管理器，eval 调用在 langfuse 侧追加 `model:<名字>` tag，可按模型过滤 trace。退役一次性脚本 `scripts/compare_models.py` / `ping_models.py` / `merge_compare_reports.py`。
- **add(ci)**：新增手动触发的评测 workflow（`.github/workflows/evals.yml`），百炼 key 跑 regression 集，HTML 报告传 artifact；可选配 `LANGFUSE_PUBLIC_HOST` secret 让 CI 运行也上报 trace。
- **fix(infra)**：修复 langfuse trace 全部静默丢失——ClickHouse limit 1536Mi 触顶，OvercommitTracker 杀掉一切写入/读取（worker 日志 `dropped N traces record(s)`）；clickhouse 内存上调至 2560Mi 并 helm upgrade，写入读取已恢复（详见 docs/langfuse.md 踩坑记录）。
- **docs(evals)**：补 2026-08-13 百炼 5 模型横评基线（glm-5.2 / glm-4.7 / deepseek-v3.2 / qwen3-max / kimi-k2.6 × regression 12 × 3 trials）；deepseek-v3.2 核心纠错能力塌陷（pass^3 5/12），当前生产临时模型处于质量回退状态，百炼 key 恢复后建议切回 glm-5.2。
- **test**：补 compare 的 spec 解析与报告渲染单测。

### 2026-08-10 18:38

- **add(evals)**：新增场景题 Pilot v1 人工评测集，按 8 个真实口语坐标组织 24 条正例、反例和边界例；每条标注 8 维分数、硬规则预期、失败标签与人工理由。
- **add(evals)**：新增评测集 schema/配比/硬规则一致性校验器和静态 HTML 审阅页，支持按领域与样本类型筛选。
- **test**：覆盖评测集配比、纯语义失败样本、陈旧标签检测和 24 卡片审阅页渲染。

### 2026-08-09 11:11

- **fix(ai/voice)**：火山 Agent Plan 过期后，文字链路迁到阿里云百炼 `glm-5.2`，ASR/TTS 分别迁到 `qwen3-asr-flash` / `qwen3-tts-flash`；百炼与火山的 thinking/语音协议按 provider 适配，部署密钥按文字、语音、图片/视频解耦。
- **fix(corrector)**：中文/中英混合回答不再被 whitespace 短输入 fast-path 拦截；纯非英语回答强制按未完成任务低分处理，并收紧 `better ⊂ nativeVersion` 与任务信息覆盖约束。
- **fix(scenarios)**：公共题补齐新增跨进程 Mongo 租约和锁内重查，防止并发超过 taxonomy target；生成 prompt 注入同坐标已有题反例，确定性拒绝近重复并最多重试一次；换题优先避开上一题的子场景。
- **add(evals/ops)**：新增题目硬规则 grader、8 维 rubric、AI 用户模拟与人工黄金集方案；新增默认 dry-run、可按 run 回滚的超额公共题软归档脚本。
- **test**：补 provider 协议、中文边界、近重复、换题多样性、题目评测与可逆归档测试；真实百炼 TTS→ASR 闭环及生成题硬门禁验证通过。

### 2026-06-29 16:45

- **add(server)**：接入火山方舟 Agent Plan 视频任务链路。新增 `VIDEO_ENABLED` 开关、`services/volc_video.py` 异步任务适配器、`scenario_videos.py` 场景视频 OSS 持久化，场景生成时可写入 `videoKey/videoPrompt/videoStatus`；默认关闭，避免自动补题消耗视频额度。
- **add(api/web)**：`/api/scenarios/next`、`practiceSessions`、分享读取支持返回 `videoUrl`；前端新增 `PracticeMedia`，练习页和反馈页视频优先、图片兜底，视频报错自动回退图片。
- **add(ops)**：新增 `scripts/backfill_scenario_videos.py` dry-run/execute 补视频脚本；`probe_volc.py` 增加可选视频任务创建探测；schema/storage 文档补视频 key 与 OSS 路径。

### 2026-06-29 16:09

- **chore(ci)**：新增结构质量门禁。前端 `pnpm run lint` 接入 CI，并用 ESLint 限制单文件最多 500 行、函数最多 5 个入参；函数长度和复杂度作为 warning 暴露。后端新增 `scripts/check_code_quality.py`，检查业务源码单文件最多 500 行、函数最多 5 个入参，并接入 CI。
- **change(web)**：拆分 Practice 页面展示层，把反馈页和录音主视图从 `PracticePage.jsx` 抽到 `components/practice/`，主页面降到 500 行以内；反馈相关测试拆到独立文件，测试文件也降到 500 行以内。
- **change(server)**：拆分 `scenario_service.py`，将偏好匹配、场景配图、公共题池 topup 分离到独立 service 模块，原入口继续 re-export，保持调用方兼容。

### 2026-06-21 16:14

- **chore(ci)**：**后端接入覆盖率统计 + CI 门槛**（原来只有前端有）。加 `pytest-cov`，`pytest` 默认带 `--cov --cov-fail-under=80`；纯外部 IO 适配器（wanx 文生图 / transcriber ASR，测试里整个 mock）从统计 omit，门槛守护真正的业务逻辑。后端整体 **84.67%**。
- **test(server)**：补 corrector **追问对话**逻辑单测（`_followup_context` / `_build_followup_messages` / `followup_chat_stream` 的上下文拼接、历史角色映射、空问题、流式 chunk/done、异常→error）+ 场景 points 注入。corrector.py 65% → **98%**。
- **test(web)**：核心用户路径补测，整体 66% → **89%**——
  - PracticePage（练习主流程：录音/转写/流式评估/三轮/追问/收录）49% → **90%**；
  - SessionDetailPage（分享开关/复制/取消、追问、tab 切换）40% → **84%**，SessionView 76% → **94%**；
  - RecordingPlayer（播放/暂停/进度/seek/事件）40% → **97%**；
  - 新增 `api/client.test.js` 测 fetch 封装 + SSE 流，client.js 移出 coverage 排除，**99% 行覆盖**。
- **change(ci)**：前端覆盖率门槛从 60/60/50/60 提到 **statements 80 / lines 85 / functions 75 / branches 72**，锁定新基线。

### 2026-06-21 16:00

- **change(share)**：分享 token 改为**纯字母数字**（`A-Za-z0-9`，12 位 ≈ 62^12，加唯一性校验兜底），去掉原 `token_urlsafe` 带的 `-`/`_` 特殊字符。
- **change(share)**：取消分享**只置 `shared=False`、保留 token**（原来是 `$unset` 清掉）。再次开启即复用同一链接、旧链接复活，不再出现"取消后链接永久失效"。
- **change(ui)**：详情页分享区从 hero 角落改为 hero 下方**清晰状态栏**：已分享=彩色底（蓝点 + "Shared · anyone with the link can view" + 复制/取消）；未分享=中性无色（"Not shared · only you can see" + Share 按钮）。
- **test**：更新分享集成测试——token 纯字母数字断言、取消后旧链接 404 但 token 保留、再开复用同一 token 复活。后端 86 / 前端 114 全绿。

### 2026-06-21 15:43

- **fix(ui)**：「Ask the coach」追问输入框高度太矮（单行 ~48px），给共用样式 `.fb-chat-input textarea` 加 `min-height: 72px`（约 3 行）、`max-height` 放宽到 160px。详情页与练习反馈页共用同一套样式，一处生效两处。

### 2026-06-21 15:31

- **add(share)**：练习**分享链接**功能。详情页点「Share」生成随机 token（`secrets.token_urlsafe`，不可枚举、可撤销），复制内容含文案+链接（`I practiced "..." on SpeakUp (IELTS x.x) — take a look 👉 <url>`）。任何人无需登录打开 `/s/:token` 即可看完整练习（场景/三轮 transcript/评分/纠错/追问对话/录音，与本人一致，含分享者昵称）。新接口：`POST`/`DELETE /api/practice-sessions/{pid}/share`（开启/撤销，校验归属、幂等）、公开只读 `GET /api/share/{token}`（无鉴权，解析昵称）；list 加 `sharedOnly` 参数。`practiceSessions` 补 `shareToken`/`shared`/`sharedAt` 字段。
- **add(share)**：分享管理——History 列表对已分享练习加「Shared」角标；Profile 加「My shares」入口 → 新页 `ManageSharesPage` 集中列出已分享练习，可逐条复制/取消分享。撤销即清 token，旧链接立即 404。
- **change(ui)**：详情页三轮 attempts 从一长条竖向堆叠改为 **Attempt 1/2/3 tab 切换**（默认选最新一轮）。抽出 `SessionView` 公共展示组件供详情页与分享页共用；分享页 `readOnly` 模式隐藏追问输入框（chat 只读）与付费 TTS 朗读按钮（防陌生人刷量），保留免费录音播放。
- **chore(docs)**：AGENTS.md 注意事项明确「**界面文案统一英文**」（按钮/标签/提示/空状态，代码注释仍中文）；`schema.md` practiceSessions 补分享字段说明。
- **test**：新增后端 6 个分享集成测试（开启/幂等/撤销失效/非 owner 404/无效 token 404/sharedOnly 过滤）+ 前端 SharePage / ManageSharesPage / `lib/share` 测试，详情页测试更新为 tab 切换断言。修 `SessionDetailPage` 在 `getPractice` 返回 null 时读取 `s.shared` 报错。本地端到端实测（隐身窗口打开分享链接、撤销后 404）通过，后端 86 / 前端 114 全绿，build 与覆盖率门槛通过。

### 2026-06-20 11:35

- **add(chat)**：追问框补到**历史详情页**（SessionDetailPage），针对该次练习最新一轮，和练习反馈页共用同一端点 + 同一份 `attempt.chat`——结果页和历史页现在一致，从历史也能发起/继续对话。旧轮次的追问保持只读回看。
- **fix(ui)**：追问区 UI 标签从中文改回**英文**（`Ask the coach` / `Thinking…` / 英文 placeholder），与全站英文外壳一致。之前误用中文是因为 `spec.md` 旧约定写成"中文界面"，实际全站早已英文。
- **chore(docs)**：修正 `spec.md` 界面语言约定——明确「**英文外壳 + 中文讲解**」：UI 标签/按钮/提示英文，AI 讲解内容（summary / gap why / 追问回答）中文，地道表达本身英文。

### 2026-06-20 11:11

- **add(chat)**：拿到反馈后可**继续追问 AI**（流式对话）。新端点 `POST /api/correct/chat/stream`：以场景+本轮反馈（native 版/gaps/小结）为上下文，把追问历史+新问题喂给 glm-5.2，SSE 纯文本流式回答；问答落进对应 attempt 的 `chat` 数组，刷新/历史页可回看。后端 `corrector.followup_chat_stream`，前端 `client.chatStream` + Practice 反馈页底部追问区（流式追加、Enter 发送）+ 历史详情页回看。提示词约束纯文本无 markdown。本地实测端到端流式+落库正常，新增 4 个集成测试，前后端测试全过（后端 80 / 前端 101）。
- **chore(docs)**：`scenario-mode.md` 模型清单/流程图更新为 glm-5.2 + 追问端点；`schema.md` attempt 补 `chat` 字段、category 枚举补 `task`。

### 2026-06-20 10:57

- **change(corrector)**：纠错提示词全局梳理后补两处缺口。①新增**任务目标判定**为首要维度：模型先拿场景 `mission`/`points` 对照学习者的话，跑题/漏关键诉求/没办成 → 作为第一个 gap（新 `category: "task"`，排最前）并在 summary 点出；②收紧"漏纠真错误"——把"宁缺毋滥/native 不皱眉就放过"改成「错就必纠（语法/时态/语序/重复啰嗦/中式搭配/用错词），只跳过两种说法都对的纯口味替换」，修掉旧 Qwen 漏纠 `help me to take me a photo` 这类真错的问题。③重说轮 `passed` 判定纳入任务完成度——任务没办成绝不判 pass。`GapItem.category` 枚举加 `task`（前端不展示 category，向后兼容）。实测 4 类场景（跑题/真错误/时态复数/本来就对）行为均正确。

### 2026-06-20 10:39

- **change(llm)**：文字/对话评估从阿里云 DashScope Qwen 切到**火山方舟 Coding Plan glm-5.2**（订阅制，成本远低于按量 Qwen——之前一天烧几十块主要是它 + 文生图）。开 thinking 模式（`extra_body.thinking.type=enabled`，实测 JSON 仍干净解析、流式不漏推理内容）。
- **change(config)**：env 命名按能力解耦、不再绑运营商——`CHAT_*`（文字 LLM）/ `IMAGE_*`（图片）/ `VOICE_*`（ASR+TTS）三组，各带独立 key + base_url，将来换 Deepseek / 别家只改 `.env` 值不动代码。删除旧的 `DASHSCOPE_*` 变量名。`corrector.py`/`scenario_service.py` 走 `CHAT_*`，`wanx.py` 走 `IMAGE_*`，`transcriber.py`/`tts.py` 走 `VOICE_*`。
- **change(cost)**：新增开关 `IMAGE_ENABLED`，**默认 `false` 关闭文生图**（成本高，暂不生成配图）。关闭时定制题/补题跳过万相调用，`imageKey` 置空，前端按无图渲染；图片接口代码与配置全部保留，设 `true` + 填 key 即恢复。
- **chore(ci)**：`docker-compose.yml` + CI「Write server .env」同步改用新变量；新增 GitHub Secret `CHAT_API_KEY`（火山 key），图片/语音复用现有 `DASHSCOPE_API_KEY` secret 值写入 prod 的 `IMAGE_API_KEY`/`VOICE_API_KEY`。`llm_audit` 价表加 `glm-5.2`（订阅制记 0）。

### 2026-06-20 08:46

- **chore(ci)**：CI 用的几个 GitHub Action 升到跑 Node 24 的版本，消除 runner 的「Node.js 20 is deprecated」警告（node20 actions 仍被强制跑在 node24 上，2026 起会移除）。`pnpm/action-setup@v4 → v6`、`docker/login-action@v3 → v4`、`docker/build-push-action@v6 → v7`（三者分别在 v6/v4/v7 起改用 node24）。`shimataro/ssh-key-action@v2` 已是 node24、`actions/checkout@v5` / `setup-node@v5` / `setup-uv@v7` 也都 node24，不动。剩下日志里的 `DEP0040 punycode` / `DEP0169 url.parse` 是 docker action 内部依赖的 node 警告，非本仓库可控。

### 2026-06-20 08:42

- **chore(docs)**：`SPEC.md`（产品功能文档）归档进 `docs/design/spec.md`，和 schema / ids / storage 等设计文档放一起。同步改两处引用（`design/app.jsx` 画布副标题、本文件历史条目 §330 指针），AGENTS.md 的 `docs/design/` 目录树补一行。文档本身内容不变，只挪位置。

### 2026-06-20 08:36

- **chore(docs)**：CHANGELOG 时间戳规则从「本地时区」改为「北京时间 UTC+8」，避免 agent 在 UTC 容器里跑出错时区。`CONTRIBUTING.md`「CHANGELOG 格式」段给出取北京时间的命令（`TZ='Asia/Shanghai' git show -s --date=format-local`），`CHANGELOG.md` 顶部说明同步。

### 2026-06-20 08:33

- **fix(ui)**：History 列表标题横向显示不全。之前时间（`history-meta`）和标题在同一行抢横向空间，长标题被截断。把时间挪到标题下方（与 attempts / gaps chip 同一 `history-sub` 行），标题独占整行宽度；同时 `history-headline` 允许换到两行（`line-clamp` 1→2），长标题展示更完整。删掉空的 `.history-meta` 样式。

### 2026-06-19 16:22

- **chore(docs)**：抽出 `CONTRIBUTING.md`（82 行）—— AGENTS.md 里通用的开发流程 / 测试分层 / CHANGELOG 格式 / PR 约定 / 工程规则（URL 状态可还原 / 测试是代码 / LLM 调用成本）都挪过去（人 + AI agent 共用）。AGENTS.md 瘦身到 141 行（原 201），只留 agent 专属的硬上下文（敏感信息 / 部署运维 / SSH / 凭据旋转 / agent 卫生约束）。README 加贡献入口链接。

### 2026-06-19 16:03

- **fix(corrector)**：风格优化不再算 gap。`I'm a software engineer` → `working as a software engineer` 这种纯地道化替换不再被标——只有真错（语法 / 用错单词 / native 听了会困惑）才算 gap。0-2 个 gap 都行，宁缺毋滥；答得到位时 summary 用鼓励代替挑刺。
- **test**：测试 cost-guard 加严。`conftest._no_real_llm` 默认 stub 所有外部出口（LLM / 万相 / CosyVoice / ASR / OSS upload），新加测试漏 patch 也不会误调真接口。76 测试仍全过。

### 2026-06-19 15:58

- **test**：补 TTS 路径 + practiceId 透传 + tts.js 关键 bug 回归测试（后端 +6 / 前端 +7）。覆盖 `_cache_key` session/全局两分支、路由 practiceId 透传、tts.js 不阻塞 play 与 30s 超时、urlCache 按 (practiceId, text) 分键、空文本不调后端、SpeakBtn practiceId prop 透传。

### 2026-06-19 15:50

- **change(tts)**：朗读音频挪到 session 下 `practiceSessions/{practiceId}/tts/{sha1}.mp3`（之前 `tts/{sha1}.mp3` 全局）。LLM 个性化生成的 nativeVersion / gap.better 几乎不跨 session 撞同句，全局缓存命中率约等于 0；挂 session 下让所有资源结构对齐（题目图在 `scenarios/`，session 内的录音 + 朗读都在 `practiceSessions/`）。session 内重听仍按 hash 复用 OSS 缓存。`/api/tts` 接受可选 `practiceId`；前端 `SpeakBtn` 接受 `practiceId` prop，PracticePage / SessionDetailPage / ReviewPage 各调用点都传了。

### 2026-06-19 15:35

- **fix(ui)**：TTS 喇叭"一直生成中"。`tts.js` 之前 `await audio.play()` 阻塞，浏览器音频缓冲卡死时 `SpeakBtn` 永远停在 loading。现在合成完拿到 URL 立刻退 loading，play() 不阻塞；合成本身加 30s 超时兜底。
- **fix(ui)**："Say this" 行高被喇叭顶高。把行内喇叭按钮压扁（30×30，原 40×40），并把这一行 `align-items: center`，文字与按钮居中对齐。
- **change(ui)**："You said" 卡片样式同 native version：去灰底改细边框、字号 17→19px、字重加粗、颜色黑色——与 native version 视觉对齐，区别只在颜色（黑 vs 蓝）。
- **change(ui)**：TTS 喇叭 loading 态从纯转圈 → 三个跳动的点（更像"生成中…"，不像加载失败）。
- **fix(ui)**：`Gaps · 2` 含义不清，改成 `Gaps · N total`。

### 2026-06-19 15:15

- **fix(practice)**：结果页刷新不再丢。评估完成后 URL 带 `?result=1`，刷新时若已有 attempt 则从最近一轮重建反馈视图（成绩 / native version / gaps / 用户原录音回放），不再回到初始录音态。AGENTS.md 加规则：页面关键状态必须可被 URL 还原。
- **change(ui)**：场景卡 Place / Scene 字体统一放大。两块字号 16px → 19px（与 native version 一致）、去掉标签灰底色、颜色统一为深色。

### 2026-06-19 13:36

- **chore**：`docker-compose.yml` 默认 `IMAGE_MODEL` 改 `wanx2.1-t2i-turbo`（之前 `wan2.7-image`），与 `config.py` 默认对齐。生产 `.env` 已覆盖，此改动让新机器 / 没设 env 覆盖的部署也默认便宜款。

### 2026-06-19 13:25

- **add**：成本报表脚本 `scripts/cost_report.py`——从 `llmCalls` 审计表按天 / kind / 模型汇总花了多少钱，`--days N` 看最近 N 天。
- **add**：本地→生产同步脚本 `scripts/sync_public_scenarios.py`——把本地 dev 生成好的公共题（文档 + OSS 图）同步到生产，避免在生产重新调 LLM/万相花钱。默认 dry-run，真写要 `--execute` + 配 `PROD_SYNC_MONGO_URI`。
- **change**：`IMAGE_MODEL` 默认值改 `wanx2.1-t2i-turbo`（之前 `wan2.7-image`），生产不改 env 也自动用上便宜款。

### 2026-06-19 13:10

- **add**：LLM/图片调用审计表 `llmCalls`——每次调 qwen / 万相都记一行（prompt + raw response + tokens + 估算成本 + 耗时），用 `linkedTo` 挂到 scenarioId / sessionId / round / userId，方便事后查"为什么这道题烂 / 评估为什么漏抓错"。包装在 `services/llm_audit.py`，写库失败只 warning 不阻塞主路径。schema 见 `docs/design/schema.md`。
- **add**：成本字段 `llmCalls.cost`（元），按 `llm_audit.py` 里的 `TEXT_PRICING` / `IMAGE_PRICING` 估算。
- **change**：图片成本优化。`IMAGE_MODEL` 从 `wan2.7-image`（约 ¥0.30/张）换 `wanx2.1-t2i-turbo`（约 ¥0.14/张，省约 50%）；分辨率从 `1280*720` 降到 `1024*576`。`wanx.py` 同时支持同步（老模型）和异步轮询（新一代便宜模型）两套 endpoint，按模型名自动选。

### 2026-06-19 12:45

- **change(prompts)**：`corrector` `SYSTEM_PROMPT` / `RETRY_PROMPT` 全部翻成中文（生产 prompt，不只是展示）。中文 prompt 让 LLM 输出中文 summary / why 更稳定，不再偶尔英文化。
- **change(scenario gen)**：prompt 加紧约束——禁场景设在考场 / 课堂 / 语言考试（修 travel.memorable_trip 出"雅思考场"那个 bug）；禁列三点演讲式指令；imagePrompt 规则放宽——从"no faces close-up"（被 LLM 误读为 no people）改成"必须展示场景核心动作和人物，用广角 / 侧面 / 背影避免 close-up 脸"。
- **fix(scenario yaml)**：scrub `scenario_taxonomy.yaml` 注释里的 `IELTS` / `雅思`字样，避免 LLM 把 sub.note 里的"IELTS P2 经典"当成场景设定。

### 2026-06-19 11:14

- **change(scenario gen)**：同 gap 内 random shuffle，避免空池子时所有人都先生成 `bank.*` / `biz.*`（字母序前缀）；不同 gap 之间仍确定性（缺得越多越先补）。
- **fix(script)**：`generate_public_scenarios.py` 输出 bug——原来 print 调用了一次 `undercovered_subs`（拿到一个 shuffle），`topup_public_scenario` 内部又调了一次（拿到另一个 shuffle），打印的 sub 跟实际入库 category 对不上。改成只调一次，print 用 doc 结果。
- **add(docs)**：`docs/design/scenario-taxonomy.md`——讲清楚公共题不是手工写的，是系统按 yaml 自动调 LLM 生成的；含扩容步骤、prompt 调优 dry-run 流程、给后续 agent 的注意事项。
- **add(dev)**：`scripts/preview_scenarios_html.py` / `llm_breakdown_html.py` / `corrector_breakdown_html.py`——dry-run 渲染 HTML 给人眼审，拆解一次真实 LLM 调用的输入/输出色块对比。
- **chore(changelog)**：Unreleased 段开始按日期分组（2026-06-19 + Earlier），后续进一步精确到分钟。

### 2026-06-19 11:04

- **add**：公共题库主题坐标系 `server/data/scenario_taxonomy.yaml`——16 大类 × 67 个子场景，覆盖中国成年人日常英语真用得到的处境（旅游 12 / 社交 8 / 工作 5 / 餐饮 5 / ...），含 16 个本土化补丁（火锅 / 春节亲戚 / 996 / 微信支付等 IELTS+CEFR 不会有的）。来源：IELTS Speaking Part 1/2/3 + CEFR Companion 2020 + 中国本土化。
- **add**：公共题自动补题（按 yaml 坐标系）——`scenario_service.topup_public_scenario()` 找 `actual<target` 的子场景，调 LLM 按坐标编故事 + 万相配图入库；`scenarios` 集合新增 `category: {domain, subId}` 字段。
- **add**：取题钩子顺带补公共池——`/api/scenarios/next` 触发的 `_maybe_topup` 后台任务原本只补用户定制题，现在同时检查公共池缺口并补一道（每次最多 1 道，全 sub 达 target 后短路，可控成本）。
- **fix(test)**：`conftest._no_real_llm` 同时 patch `services.scenario_service._get_client`（之前只 patch corrector 模块的，scenario_service 的本地引用漏了——背景 topup 任务可能在测试结束后真调 LLM）。

**Earlier**

- **错题本可取消收录**：反馈页每条 gap 的收录按钮从只读「Saved」改成可点切换——`+ Add to Review` / `✓ In Review`（英文，对齐底部 Review tab，明确收录去向），再点一下即从错题本移除。AI 自动收录的 gap 现在也回传 `reviewItemId`（`POST /api/correct` 把 id 回写进 gap，`POST /api/review-items` 返回 `ids` 列表），所以自动收录的同样能取消。
- **朗读按钮播放态**：`SpeakBtn` 增加 idle/loading/playing 三态，播放中显示停止图标 + 实心高亮，再点即停（`tts.js` 暴露 `stop()` 并返回 Audio 实例供监听 ended/pause）。
- **自定义录音回放** `RecordingPlayer`（蓝色播放/暂停键 + 进度条 + 时间）：替换 history 里的浏览器原生 `<audio controls>`；结果页评估完也用本地录音 object URL 即时展示回放——两个页面播放控件统一。新增 `play`/`pause` 图标。
- **新增 3 道公共场景题**（LLM 生成 + 万相配图）。
- **首页「换一道题」按钮**（底部录音按钮下方的药丸按钮 `Try another scenario`）：点了跳到下一题，当前题记进本会话 skip 列表（sessionStorage，刷新也不再返回）。`GET /api/scenarios/next` 支持 `exclude=` 参数排除指定 scenarioId。
- **LLM 批量出题脚本** `scripts/generate_public_scenarios.py`：重写为按 yaml 坐标系驱动——找 gap 最大的 sub → LLM 编故事 → 万相配图 → 入库；保留 `--dry-run` 只看文案不花生图钱。原来按 `KIND_ROTATION` 随机轮换的实现已替换。
- **雅思口语评分**：每次评估额外给一个 0~9（0.5 进制）的 IELTS band 分，反馈页 / 历史详情顶部大字号展示，存进 attempt。
- **CosyVoice 朗读**（替换浏览器内置 TTS）：新增 `POST /api/tts`，DashScope CosyVoice 合成英文朗读，按「模型+音色+文本」哈希缓存到 OSS（`tts/<sha1>.mp3`），同一句话第二次直接走缓存不再花钱；前端点击喇叭才请求合成。

### Added (tests)
- **前端行为测试全面补齐**：为所有页面（`PracticePage`、`HistoryPage`、`ReviewPage`、`SessionDetailPage`、`ProfilePage`）和核心组件（`SpeakBtn`、`RecordingPlayer`、`Layout`）新增 `.test.jsx`，共 92 个测试覆盖 happy path + 关键交互（换题、复习流程、删除确认、分页等）。
- **前端覆盖率门槛**：`vite.config.js` 新增 coverage 配置（`@vitest/coverage-v8`），对业务逻辑代码设置 statements/lines/functions ≥60%、branches ≥50% 的强制门槛；CI `test-web` job 新增 `pnpm test:coverage` 步骤，未达标阻断部署。
- **AGENTS.md 开发流程更新**：明确前端测试为强制步骤（任何改动都要跑 `pnpm test`，有前端改动还要跑 `pnpm test:coverage`），checklist 新增「对应 `.test.jsx` 文件」和「`pnpm test:coverage` 通过」两项。

### Fixed
- **ProfilePage 空用户崩溃**：退出登录后 React 短暂以 `user=null` 重渲染 `ProfilePage`，访问 `user.phone` 抛错。加 `if (!user) return null` 守卫修复。
- **反馈页「下一题」重复给同一道**：feedback 阶段的 "Next scenario" / "Next" 按钮调用 `startNewRound` 时未传当前 `scenarioId`，当前题不进 skip 列表，后端可能立刻给回同一道。改为 `startNewRound(session?.scenarioId)`，与 ready 阶段的「换一道题」按钮行为一致。
- **换题反复给同一道**：取题逻辑原本是确定性的——fresh 池排序后永远取 `pool[0]`，全练过后的兜底用 `user_id+日期` 哈希（同一天恒定同一题），且兜底池没排除当前题。改成分层候选（没练过且没 skip → 没练过 → 没 skip → 全池），每层内 `random.choice`，且 skip/当前题为硬约束：只要库里还有别的题，绝不返回刚跳过的那几道。
- **History「load more」要点很多次**：后端 `GET /api/practice-sessions` 之前返回所有 session（含只看图没说话的空记录），前端再二次过滤——常常一页 20 条滤剩没几条，得反复点。改成数据库查询层就只返回 `attempts` 非空的记录，一次稳定给 20 条真历史；前端去掉冗余过滤、`hasMore` 判断也准了。

### Changed
- **评估 prompt 收紧**（`corrector.py`）：`nativeVersion` 必须是「学习者原话的直接改写」、最多 3 句；gap 上限 2 条、优先 1-3 词的小修；每个 gap 的 `better` 必须逐字出现在 `nativeVersion` 里（gap 与地道版对齐）。出题脚本同步要求「任务 3 句话以内能答完，points 2-3 个」。
- **反馈页 gap 卡视觉**：`Gaps · N` 字号 17→20 加粗、与上方多 22px 间距；gap 三行做成**细线表格**（行间 + 标题下 1px 浅色分隔线）；三列正文字号统一 16px（差异只靠颜色/加粗）、标签统一 14px；**局部红**——只把 You said 标签标红、正文保持中性，不整行飘红。history 详情页 gap 同步加 `is-said`/`is-fix`，与结果页一致。
- **结果页场景图高度还原**：`.fb-img img` 去掉 `max-height:180px`，改回与起始页一致的 `aspect-ratio:1/1` 正方形。
- **评估时自动滚到进度处**：点 Get feedback 后页面自动 `scrollIntoView` 到流式进度文字，移动端不再需要手动下滑才能看到 token 回显。
- **「练过」判定收紧**：取题时只把「开口评估过至少 1 次」（`attempts` 非空）的题视为练过、不再返回；只看了图没说话的不算，下次还会再出。
- **Profile 页精简**：删掉无用的 Speech / All platforms / Version v0.1·DEMO 信息块。
- **新用户昵称英文化**：注册昵称 `用户xxxx` → `Userxxxx`。

### Changed
- **首页/反馈页图片留出左右内缩**（不再贴满边缘），与下面文字描述之间多 16px 间距，整体不再挤。
- **History 时间格式 + 布局**：日期改 `YYYY-MM-DD HH:MM:SS`（含秒），独立放到行右侧，左侧只留标题/chip，不再左堆一团；session 详情页同步换格式。
- **反馈页 / 详情页文案微调**：
  - `Gaps · N` 标题字号 14→17、颜色 `--ink-3`→`--ink`、加粗
  - gap 卡里的 `解释` 改成英文 `Why`（这是英文学习产品，标签都英文化）
  - `You said` 标签颜色从 `--ink-3` 提到 `--ink-2`、原说法本身从 `--ink-2` 提到 `--ink`，不再灰得看不见
- **喇叭按钮显示「合成中」**：未缓存的文本点击后按钮变 spinner 直到合成 + OSS URL 拿到，播放开始才恢复；缓存命中保持秒响应；按钮 hit-area 加大到 40×40。
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
- **差距框架（gap-exposure）** 取代"纠错"作为产品本质 — see `docs/design/spec.md` §2（原 `SPEC.md`，2026-06-20 归档）
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
