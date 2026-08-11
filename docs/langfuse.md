# Langfuse（自托管 LLM 观测）

2026-08-11 部署，为 speakup（及后续 video-2022）提供 LLM trace / 评测观测。

> 安全约定：主机 IP、密钥**不入库**。主机看本机 `~/.ssh/config` 的 `tencent-services` 别名；
> 密钥在服务器 `/opt/langfuse/values.yaml`（600 root）。

## 部署形态

- 位置：services 机（Tencent Lighthouse）的 **k3s**，`langfuse` namespace
- 安装：helm chart `langfuse` 1.5.41（app 3.224.1），values 在 **`/opt/langfuse/values.yaml`**（600 root，含全部密钥）
- 组件：web / worker / postgresql / clickhouse(单副本) / valkey / minio / zookeeper，资源按 8G 共享机裁剪过
- 存储：k3s local-path（pg 4Gi + clickhouse 10Gi + minio 10Gi + zk 2Gi + valkey 2Gi）
- 升级：重新 helm upgrade 同 values 即可；chart tgz 从 github releases 拉（服务器直连慢，本机走代理下载后 scp 上去）

## 访问

- 公网入口（2026-08-11 起）：`http://<services 机公网 IP>:30030` —— NodePort 30030
  （values 里 `langfuse.web.service.type/nodePort` 管理），Lighthouse 防火墙已放行 TCP 30030。
  ⚠️ 明文 HTTP：登录密码和 trace 内容不加密，用户已知晓并接受；要加密就加域名走 caddy（见下）
- UI/API 集群内入口：`langfuse-web` svc ClusterIP（svc 重建会变；查询：
  `sudo k3s kubectl get svc -n langfuse langfuse-web`）
- 本机看 UI（不走公网）：`ssh -L 3000:<ClusterIP>:3000 tencent-services` 后开 http://127.0.0.1:3000
- 若以后要 HTTPS：DNS 加 `langfuse.a4.fit` A 记录 → services 机公网 IP，/opt/caddy/Caddyfile
  仿照 multica.a4.fit 加 `reverse_proxy <ClusterIP>:3000`，改完 `docker exec caddy-caddy-1 caddy reload --config /etc/caddy/Caddyfile`，
  并把 values.yaml 的 `nextauth.url` 改成该域名后 helm upgrade
- 登录：admin@a4.fit / 密码见 `/opt/langfuse/values.yaml` 的 LANGFUSE_INIT_USER_PASSWORD
- 已关闭公开注册（signUpDisabled）；org=personal，project=speakup

## speakup 埋点

- 适配层：`server/services/llm_trace.py`（Langfuse SDK v4），在 `llm_audit` 漏斗统一双写
- 未配 `LANGFUSE_*` env 整体 no-op；异常只 warn 不抛
- 生产 env 由 CI 写 .env（GitHub Secrets `LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY`），
  HOST 当前是 langfuse-web 的 ClusterIP（speakup 容器经宿主机路由可达）；DNS 配好后建议换成 https://langfuse.a4.fit
- eval 调用（link_to 带 eval_task）进 **environment=eval**，和线上流量隔开
- 本地跑 evals 要上报：先 ssh -L 转发，再 server/.env 配 `LANGFUSE_HOST=http://127.0.0.1:3000` + 两个 key

## 踩坑记录

- **web pod init 阶段 V8 堆 OOM（CrashLoopBackOff）**：默认 limit 1Gi 不够，Node 默认堆 512MB。
  解法：web `NODE_OPTIONS=--max-old-space-size=1536` + limit 2Gi（worker 1024/1.5Gi），已写在 values.yaml
- chart 默认 clickhouse `replicaCount: 3` + `resourcesPreset: 2xlarge`，单机必须裁成 1 副本 + 显式小资源
- 服务器 helm 直连 github releases 拉 chart 会挂起（不是 404，是慢到超时）；本机走代理下载再 scp
