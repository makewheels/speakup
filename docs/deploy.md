# 部署指南

> 敏感值（IP/域名/密钥）全走 GitHub Secrets，不在本文档出现。
> 各 Secret 的名字见 `.github/workflows/ci-cd.yml` 和仓库 Settings → Secrets。

## 架构

```
GitHub Actions → 构建 Docker 镜像 → 推 ACR (b4/speakup)
                               → SSH 到生产机 → docker compose pull && up
<生产域名> → /opt/caddy 网关 (Caddy, 80/443) → speakup:3001 (docker network: edge)
speakup:3001  → MongoDB (内网, MONGO_URI)
                                 → 阿里云 OSS speakup-prod 桶
                                 → 阿里云百炼 glm-5.2 / Qwen ASR / Qwen TTS
                                 → 火山方舟 Seedream（配图，默认关闭）
```

AI 能力按环境变量解耦：文字使用 `CHAT_*`，语音使用 `VOICE_*`，配图使用 `IMAGE_*`。当前生产文字模型是百炼 `glm-5.2`，ASR/TTS 分别为 `qwen3-asr-flash` / `qwen3-tts-flash`；配图因原套餐失效设置 `IMAGE_ENABLED=false`，已有题图不受影响。

**多服务部署的核心约定**（这台机以后会跑多个服务）：

- `/opt/caddy/` 是**唯一**占 80/443 的网关，独立 compose，独立 Caddyfile，由人工/单独的 caddy 仓库维护
- 每个业务服务（如 speakup、article2audio）的 compose **不暴露宿主端口**，只 `expose` 内部端口
- 业务和 caddy 通过 docker external network `edge` 通信
- 加新服务步骤：
  1. 业务 compose 接入 `networks: [edge]` + `external: true`
  2. `/opt/caddy/Caddyfile` 加一段 `<域名> { reverse_proxy <服务名>:<端口> }`
  3. `docker compose -f /opt/caddy/docker-compose.yml exec caddy caddy reload --config /etc/caddy/Caddyfile`

- **镜像仓库**：阿里云 ACR 个人版 (cn-beijing)，`b4/speakup` 存应用镜像。caddy 等公共镜像走 docker.io，靠生产机 docker daemon 配置的 **registry-mirrors** 拉。
- **凭据**：阿里云**主账号 ACR 固定密码**（控制台 → 容器镜像服务 → 个人实例 → 访问凭证），存 GitHub Secrets `ACR_AK_ID`/`ACR_AK_SECRET`。
- **回滚**：旧 `:latest` 转 `:previous`，`docker tag :previous :latest && docker compose up -d`。

## 生产机布置

```
/opt/caddy/                    # 网关，全局唯一占 80/443
├── docker-compose.yml         # caddy 容器
└── Caddyfile                  # 所有 host 路由

/opt/speakup/                  # 业务服务
├── docker-compose.yml         # speakup 容器（CI 写入）
├── .env                       # CI 写入
└── logs/                      # 应用持久化日志（容器 /app/logs，按天切分，默认保留 30 天）

/opt/<其他服务>/                # 同上模式
```

## 首次部署

1. 阿里云控制台给主账号设 ACR 固定密码。
2. `gh secret set ACR_AK_ID/ACR_AK_SECRET`（其余 Secret 已有跳过）。
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
8. `git push master` → CI 自动构建部署。

## 回滚

```bash
ssh -i ~/Downloads/qcloud_lighthouse_beijing ubuntu@<HOST>
cd /opt/speakup
IMG=registry.cn-beijing.aliyuncs.com/b4/speakup
docker tag $IMG:previous $IMG:latest
docker compose up -d
```

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
