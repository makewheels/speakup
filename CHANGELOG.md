# Changelog

All notable changes to SpeakUp will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning follows [SemVer](https://semver.org/).

## [Unreleased]

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
