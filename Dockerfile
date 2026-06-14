# ---- 前端构建 ----
FROM node:22-slim AS web
RUN corepack enable && corepack prepare pnpm@10 --activate
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm run build

# ---- 后端 + 托管前端静态 ----
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev
COPY server/ ./
COPY --from=web /web/dist ./static
ENV APP_ENV=production
# venv 直接进 PATH，启动用 venv 里的 uvicorn，不再 `uv run`
# （`uv run` 每次冷启会重新 sync + 编译字节码，拖慢启动 → 部署窗口 caddy 502）
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 3001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]
