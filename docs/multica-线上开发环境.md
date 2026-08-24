# Multica 线上开发环境（腾讯云）

> 面向在 Multica 上开发 speakup 的 agent。凭据一律不入库，本文只写约定。

## 环境概览

- Multica daemon 跑在腾讯云 `services` 机，agent runtime 现有 **Claude Code** 与 **Qwen**（Codex 已于 2026-08-19 移除）。
- agent 从 `github.com/makewheels/speakup` 克隆代码，工作区在 services 机 `/srv/multica-runtime/workspaces/`。
- 工具链：node/npm/pnpm、uv（自动拉 Python 3.14）、git、gh（已登录 makewheels）、jq、ripgrep、docker 均可用；**mongosh / 本机 mongod 缺失**（见下）。

## 测试数据库约定

- MongoDB 实例只有一个：lighthouse-2 上的 `mongodb` 容器，VPC 地址 `10.0.20.14:27017`，生产库为 `speakup`。
- 为 Multica 新建了**专用测试库 `speakup_multica_test`**，配专用低权限用户 `multica`（仅该库 readWrite）。
- 连接串由 daemon 以环境变量 **`MONGO_TEST_URI`** 注入（存于服务端 `/etc/multica-runtime/mongo.env`，600，不进 git）。agent 直接读 `MONGO_TEST_URI` 即可，**不要**在代码/.env/提交里写死或新增该连接串。
- **铁律：只读写 `speakup_multica_test`，禁止访问生产 `speakup` 库。**

## 跑测试的注意事项

`server/tests/conftest.py` 目前硬编码 `MONGO_URI=mongodb://localhost:27017/speakup-test`，而 services 机**没有本机 mongod**。因此在 Multica 上跑集成测试需二选一：

1. 在 services 机起一个绑定 `127.0.0.1:27017` 的 mongod（docker 单容器即可），测试代码零改动；或
2. 改 conftest 尊重 `MONGO_URI`/`MONGO_TEST_URI` 环境变量覆盖（更通用，但属代码改动，需走正常 PR）。

单元测试（`tests/unit/`，全 mock）不受影响，可直接跑。
