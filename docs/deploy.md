# 部署指南

> 敏感值（IP/域名/密钥）全走 GitHub Secrets，不在本文档出现。
> 各 Secret 的名字见 `.github/workflows/ci-cd.yml` 和仓库 Settings → Secrets。

## 架构

```
GitHub Actions → 构建 Docker 镜像 → 推 ACR (b4/speakup)
                               → SSH 到生产机 → docker compose pull && up
<生产域名> → Caddy (自动 HTTPS) → speakup:3001
speakup:3001  → MongoDB (内网, MONGO_URI)
                                 → 阿里云 OSS speakup-prod 桶
                                 → DashScope (Qwen 评估 + 万相配图)
```

- **镜像仓库**：阿里云 ACR 个人版 (cn-beijing)，命名空间 `b4`：
  - `b4/speakup` — 应用镜像
  - `b4/caddy` — `caddy:2-alpine` 的镜像（解决国内拉 docker.io 不通的问题；CI 第一次部署时自动从 docker.io 同步过来）
- **凭据**：阿里云**主账号 ACR 固定密码**（控制台 → 容器镜像服务 → 个人实例 → 访问凭证设置），存 GitHub Secrets `ACR_AK_ID`（用户名）/ `ACR_AK_SECRET`（密码）。
- **回滚**：每次部署前旧 `:latest` 转成 `:previous`，回滚 = `docker tag :previous :latest && docker compose up -d`。每次构建额外打 `:sha` 标签，可回退任意版本。

## 生产机布置

```
/opt/speakup/
├── docker-compose.yml
├── Caddyfile
└── .env  （由 CI 每次部署写入，不手动编辑）
```

Docker Compose 起两个容器：`speakup`（后端+前端静态，internal 3001）、`caddy`(80/443 → speakup:3001，自动签 Let's Encrypt）。

## 首次部署

1. 阿里云控制台给主账号设 ACR 固定密码。
2. `gh secret set ACR_AK_ID/ACR_AK_SECRET`（其余 Secret 已有跳过）。
3. 服务器是 Ubuntu 24.04，需预装 Docker（`sudo apt install docker.io docker-compose-v2`，Docker 29+）。
4. 腾讯云防火墙开放 22、80、443 端口（80/443 给 Caddy）。
5. `sudo mkdir -p /opt/speakup && sudo chown ubuntu:ubuntu /opt/speakup`（让 CI 能 rsync）。
6. `git push master` → CI 自动构建部署。

## 回滚

```bash
ssh -i ~/Downloads/qcloud_lighthouse_beijing ubuntu@<HOST>
cd /opt/speakup
IMG=registry.cn-beijing.aliyuncs.com/b4/speakup
docker tag $IMG:previous $IMG:latest
docker compose up -d
```

回退到某个历史版本：
```bash
IMG=registry.cn-beijing.aliyuncs.com/b4/speakup
docker pull $IMG:<sha>
docker tag $IMG:<sha> $IMG:latest
docker compose up -d
```

## 常用运维

```bash
cd /opt/speakup

# 看日志
docker compose logs -f --tail=50 speakup
docker compose logs -f caddy

# 重启
docker compose restart speakup

# 清理旧镜像
docker image prune -a -f
```

## 多服务约定

这台机以后会按端口部署多个服务。每个服务：
- 一个 `docker-compose.yml` + 各自的 Caddy（或共用一份）
- 绑定不同端口（如 speakup=3001、article2audio=8770），compose 内部端口隔离
- Caddy 按域名路由到不同容器（生产域名各服务各占一个子域，从 GitHub Secret 注入）
