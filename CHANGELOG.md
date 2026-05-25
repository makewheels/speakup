# Changelog

All notable changes to SpeakUp will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
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
