# Langfuse（自托管 LLM 观测）

2026-08-11 部署，为 speakup（及后续 video-2022）提供 LLM trace / 评测观测。

> 安全约定：主机 IP、密钥**不入库**。主机看本机 `~/.ssh/config` 的 `tencent-services` 别名；
> 组件/项目密钥在服务器 `/opt/langfuse/values.yaml`（600 root），管理员登录凭据在 `/opt/langfuse/admin-credential.json`（600 root）。

## 部署形态

- 位置：services 机（Tencent Lighthouse）的 **k3s**，`langfuse` namespace
- 安装：helm chart `langfuse` 1.5.41，web/worker 运行 `latest`（当前 app `4.10.0`），values 在 **`/opt/langfuse/values.yaml`**（600 root，含组件与项目密钥）
- 组件：web / worker / postgresql / valkey / minio，另有独立 ClickHouse `26.4.5.143` StatefulSet，资源按 8G 共享机裁剪过
- 存储：k3s local-path（pg 4Gi + clickhouse 30Gi + minio 10Gi + valkey 2Gi）；升级前备份在 `/opt/langfuse/backups/2026-08-14-pre-v4`
- 升级：`langfuse-auto-update` 每天 03:17 顺序滚动 web/worker 的 `latest` 镜像，允许跨主版本；Helm chart 和有状态组件需分开管理

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
- 登录：admin@a4.fit / 密码见 root `0600` 的 `/opt/langfuse/admin-credential.json`
- 已关闭公开注册（signUpDisabled）；org=`personal`
- 当前 SpeakUp 项目显示名为 `speakup`，项目 ID 为 `cmsrtdtfl00izw5075d19048y`；这是 Langfuse 自动生成的 ID
- 旧项目 ID `speakup`（删除前显示名 `speakup-legacy-20260814`）已完成数据库、ClickHouse 和 S3 清理，当前 Langfuse 仅有 `speakup` 和 `video-2022` 两个可用项目
- 密码认证以有效邮箱为登录标识；显示名不能替代邮箱，裸用户名 `admin` 无法用于原生登录

## speakup 埋点

- 适配层：`server/services/llm_trace.py`（Langfuse SDK v4），在 `llm_audit` 漏斗统一双写
- 未配 `LANGFUSE_*` env 整体 no-op；异常只 warn 不抛
- 生产 env 的三个 `LANGFUSE_*` 变量由 CI 通过 OIDC 从 Infisical `speakup/prod/langfuse` 读取后注入
  （不放 GitHub Secrets），HOST 当前是 langfuse-web 的 ClusterIP（speakup 容器经宿主机路由可达）；
  DNS 配好后建议换成 https://langfuse.a4.fit
- eval 调用（link_to 带 eval_task）进 **environment=eval**，和线上流量隔开
- 本地跑 evals 要上报：先 ssh -L 转发，再 server/.env 配 `LANGFUSE_HOST=http://127.0.0.1:3000` + 两个 key

## 评测配置

- 默认 Judge 模型：`dashscope/glm-5.2`，`providerOptions.enable_thinking=false`
- Evaluation rule：`Correctness`，作用于新写入的 `GENERATION` observation，状态为 `active`
- 数据集：`speakup/evals/regression-v1`（12 条）和 `speakup/evals/capability-v1`（14 条）
- 管理页面：`/project/cmsrtdtfl00izw5075d19048y/evals`
- 项目迁移只复制数据集和可执行配置；旧 legacy 项目后续已删除

## 踩坑记录

- **web pod init 阶段 V8 堆 OOM（CrashLoopBackOff）**：默认 limit 1Gi 不够，Node 默认堆 512MB。
  解法：web `NODE_OPTIONS=--max-old-space-size=1536` + limit 2Gi（worker 1024/1.5Gi），已写在 values.yaml
- v4 要求较新 ClickHouse；chart 内置旧版组件已改为独立单副本 `langfuse-clickhouse-external`，其 desired state 在基础设施仓库管理
- 当前 MinIO 的 S3 `DeleteObjects` 与 v4 SDK 默认 CRC32 不兼容；values 必须保留 `LANGFUSE_S3_DELETE_OBJECTS_CHECKSUM_ALGORITHM=MD5`
- 服务器 helm 直连 github releases 拉 chart 会挂起（不是 404，是慢到超时）；本机走代理下载再 scp
- **ClickHouse 内存墙 → trace 全部静默丢失（2026-08-13 修）**：症状是摄入返回 201 但任何读取
  404/列表接口超时。worker 日志报 `memory limit exceeded ... OvercommitTracker ... WaitForAsyncInsert`，
  `Max attempts reached, dropped N traces record(s)`。当时根因：clickhouse limit 1536Mi（max_server_memory
  ≈0.9×limit≈1.35GiB），async insert 缓冲卡死后 MemoryTracking 虚高到 1.66GiB，OvercommitTracker
  杀掉一切新查询/插入，读端也被拖死。解法：values.yaml 里 clickhouse `limits.memory: 2560Mi`、
  `requests.memory: 1Gi` 后恢复。当前外置 ClickHouse 延续 `2560Mi` limit；排查入口仍是
  `kubectl logs deploy/langfuse-worker`，凭据位于 secret `langfuse-clickhouse-external`，不要输出明文。
