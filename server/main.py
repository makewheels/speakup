import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db.connection import connect_db
from logging_config import configure_logging
from routes import (
    auth,
    correct,
    feedbacks,
    free_topics,
    practice_sessions,
    review_items,
    scenarios,
    transcribe,
    tts,
    version,
)

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield


app = FastAPI(title="SpeakUp API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(scenarios.router)
app.include_router(correct.router)
app.include_router(practice_sessions.router)
app.include_router(practice_sessions.share_router)
app.include_router(review_items.router)
app.include_router(feedbacks.router)
app.include_router(transcribe.router)
app.include_router(tts.router)
app.include_router(free_topics.router)
app.include_router(version.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}

# 生产环境 FastAPI 直接托管前端静态（Docker 里 WORKDIR=/app，static 在 /app/static）
static = Path(__file__).parent / "static"
if static.exists():
    # 显式挂 /assets，让构建产物按真实路径返回
    app.mount("/assets", StaticFiles(directory=str(static / "assets")), name="assets")

    # SPA fallback：任何未匹配 API/资源的路径都返回 index.html
    # 这样 /login /practice 等前端路由刷新不再 404
    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = static / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3001, reload=True)
