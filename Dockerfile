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
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev
COPY server/ ./
COPY --from=web /web/dist ./static
ENV APP_ENV=production
EXPOSE 3001
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]
