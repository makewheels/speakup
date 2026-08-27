# chore: Docker 镜像双推——ACR + GitHub GHCR

背景：镜像此前只推阿里云 ACR。作为开源项目应同时发布到 GitHub（GHCR）；但北京生产机从 GitHub 拉镜像很慢，因此采用双推。

## 改动（`.github/workflows/ci-cd.yml`）
- deploy job 权限加 `packages: write`。
- 新增 Login to GHCR 步骤（内置 `GITHUB_TOKEN`，无额外凭据）。
- build-push tags 双推：`ACR_IMAGE` 与 `GHCR_IMAGE` 各带 `latest` + `YYYYMMDD-HHMMSS-NNNN`。
- 清理步骤同时 `docker logout ghcr.io`。
- **生产部署不变**：仍只从 ACR 拉（北京机房快），`:previous` 回滚锚点不受影响。

## 文档
deploy.md 架构图与镜像仓库小节同步为双推。

## 说明
deploy job 只在 push master 时运行，PR 阶段跳过，因此首次双推在本 PR 合并时生效；GHCR 包可见性跟随仓库可见性。
