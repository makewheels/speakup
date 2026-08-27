# 部署指南

> 敏感值（IP/域名/密钥）统一存放在 Infisical，不在本文档或 GitHub Secrets 中出现。
> GitHub Actions 通过受仓库、分支和 audience 约束的 OIDC 身份临时读取生产配置。

## 架构

```
GitHub Actions → OIDC 读取 Infisical → 构建 Docker 镜像 → 双推 ACR (b4/speakup) + GHCR (ghcr.io/makewheels/speakup)
                                          → SSH 到生产机 → 临时注入配置 → docker compose pull && up
<生产域名> → /opt/caddy 网关 (Caddy, 80/443) → speakup:3001 (docker network: edge)
speakup:3001  → MongoDB (内网, MONGO_URI)
                                 → 阿里云 OSS speakup-prod 桶
                                 → DeepSeek deepseek-v4-flash（文字）/ 百炼 Qwen ASR / Qwen TTS
                                 → 火山方舟 Seedream（配图，默认关闭）
```

AI 能力按环境变量解耦：文字使用 `CHAT_*`，语音使用 `VOICE_*`，配图使用 `IMAGE_*`。当前生产文字模型是 DeepSeek 官方 `deepseek-v4-flash`（当前版本 DeepSeek-V4-Flash-0731），ASR/TTS 分别为百炼 `qwen3-asr-flash` / `qwen3-tts-flash`；配图因原套餐失效设置 `IMAGE_ENABLED=false`，已有题图不受影响。实际值以 Infisical 的 `speakup/prod` 为准，共享语音密钥以 `common/dev` 为准。

语音容错：云 ASR 失败时前端保留录音并进入可编辑转写框，用户手动输入后仍可完成评估；云 TTS 失败时自动改用浏览器 `speechSynthesis`。这保证主练习链路可降级完成，但不等于云语音服务健康。恢复完整云语音前需用北京地域、已开通对应语音模型的常规百炼 API Key 更新 `DASHSCOPE_API_KEY`，再分别实测 `/api/transcribe` 与 `/api/tts`，不能只看 `/api/health`。

更新 Infisical 后，从 Actions 页手动运行 `CI / CD` 工作流。任务只在部署期间创建受限临时文件，`docker compose` 完成环境解析后立即删除；生产机不再保留应用 `.env`。不要重跑更新前的旧任务，旧任务可能仍使用当时的密钥快照。

每次部署会把当前 GitHub commit SHA 作为非敏感的 `APP_VERSION` 注入容器；`GET /api/version` 必须返回该 SHA。部署烟测同时检查健康接口和版本一致性，避免镜像拉取或容器替换异常时把旧版本误报为上线成功。

## 功能完成邮件通知

`.github/workflows/feature-notify.yml` 是与部署解耦的手动工作流：只允许从默认分支运行，输入一行标题、简短说明、最多 6 个功能点、可选链接，以及 `docs/assets/feature-notifications` 下不超过 2 MB 的安全 SVG 说明图，然后发送手机友好的 HTML + 纯文本邮件。说明图以内嵌附件随邮件发送，不依赖外部图片链接。仓库不保存栅格截图；真实截图只可在操作系统临时目录用于当次人工验收或发送后即清理。工作流不随 deploy 自动触发，防止失败重跑或回滚时重复打扰收件人。

通知配置通过 GitHub OIDC 从 Infisical `speakup-secrets/prod/notifications` 读取，不使用 GitHub Secrets，也不在仓库记录收件人或凭据：

- 通用：`EMAIL_PROVIDER`、`MAIL_FROM_NAME`、`MAIL_FROM_ADDRESS`、`FEATURE_MAIL_TO`
- SMTP：`SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`
- Resend：`RESEND_API_KEY`

发送程序为 `scripts/send_feature_email.py`；SMTP 使用证书校验的隐式 TLS，Resend 请求带幂等键。两种 provider 的日志都只报成功数或脱敏错误，不输出地址、密码或 API key。

**多服务部署的核心约定**（这台机以后会跑多个服务）：

- `/opt/caddy/` 是**唯一**占 80/443 的网关，独立 compose，独立 Caddyfile，由人工/单独的 caddy 仓库维护
- 每个业务服务（如 speakup、article2audio）的 compose **不暴露宿主端口**，只 `expose` 内部端口
- 业务和 caddy 通过 docker external network `edge` 通信
- 加新服务步骤：
  1. 业务 compose 接入 `networks: [edge]` + `external: true`
  2. `/opt/caddy/Caddyfile` 加一段 `<域名> { reverse_proxy <服务名>:<端口> }`
  3. `docker compose -f /opt/caddy/docker-compose.yml exec caddy caddy reload --config /etc/caddy/Caddyfile`

- **镜像仓库（双推）**：阿里云 ACR 个人版 (cn-beijing) `b4/speakup` + GitHub GHCR `ghcr.io/makewheels/speakup`，每次部署同 tag 双推（`latest` + `YYYYMMDD-HHMMSS-NNNN`）。**生产只拉 ACR**（北京机房速度快）；GHCR 面向开源分发。GHCR 登录用内置 `GITHUB_TOKEN`（job 需 `packages: write`），无额外凭据。
- **凭据**：阿里云 ACR 登录凭据存 `speakup/prod/deployment`；runner 和生产机均使用一次性 Docker 配置目录，任务结束即清理。
- **回滚**：旧 `:latest` 转 `:previous`，`docker tag :previous :latest && docker compose up -d`。

## 生产机布置

```
/opt/caddy/                    # 网关，全局唯一占 80/443
├── docker-compose.yml         # caddy 容器
└── Caddyfile                  # 所有 host 路由

/opt/speakup/                  # 业务服务
├── docker-compose.yml         # speakup 容器（CI 写入）
└── logs/                      # 应用持久化日志（容器 /app/logs，按天切分，默认保留 30 天）

/opt/<其他服务>/                # 同上模式
```

## 首次部署

1. 在 Infisical 建立 `speakup` 的 dev/prod 目录和只读 GitHub OIDC 身份。
2. 将 ACR、SSH、数据库、OSS、LLM 和 Langfuse 配置分别录入对应目录；GitHub 仅保存非敏感的 Infisical 地址与 audience 变量。
3. 服务器装 Docker（`sudo apt install docker.io docker-compose-v2`）。
4. 配 docker daemon 镜像加速器：
   ```bash
   sudo tee /etc/docker/daemon.json <<EOF
   {
     "registry-mirrors": [
       "https://docker.m.daocloud.io",
       "https://docker.nju.edu.cn",
       "https://dockerproxy.com"
     ]
   }
   EOF
   sudo systemctl restart docker
   ```
5. 腾讯云防火墙开放 22、80、443。
6. 建 `/opt/caddy/`：
   ```bash
   sudo mkdir -p /opt/caddy && sudo chown ubuntu:ubuntu /opt/caddy
   cd /opt/caddy
   # 写 Caddyfile（每个 host 一段 reverse_proxy）和 docker-compose.yml
   # docker-compose.yml 创建 external network: edge
   docker compose up -d
   ```
7. 建 `/opt/speakup/`：`sudo mkdir -p /opt/speakup && sudo chown ubuntu:ubuntu /opt/speakup`
8. `git push master` → CI 自动构建部署；成功后确认生产机不存在应用 `.env` 和持久化 registry 登录文件。

## 回滚

回滚也必须从带 Infisical OIDC 注入的流水线执行，不能依赖服务器上的明文 `.env`。流水线在每次部署前保留 `:previous` 镜像作为一步回滚锚点。

## 常用运维

```bash
# 业务日志
docker compose -f /opt/speakup/docker-compose.yml logs -f --tail=50

# 持久化应用日志（跨容器重建保留）
tail -f /opt/speakup/logs/speakup.log

# 按事故日期回看历史日志
ls -lh /opt/speakup/logs/
grep -n "duration_ms\\|error\\|ps_" /opt/speakup/logs/speakup.log*

# 网关日志
docker compose -f /opt/caddy/docker-compose.yml logs -f

# Caddyfile 改完热加载（不重启容器）
docker compose -f /opt/caddy/docker-compose.yml exec caddy \
  caddy reload --config /etc/caddy/Caddyfile

# 清理旧镜像
docker image prune -a -f
```
