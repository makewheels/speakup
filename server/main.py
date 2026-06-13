import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.connection import connect_db
from routes import auth, correct, practice_sessions, review_items, scenarios


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
app.include_router(review_items.router)

# 生产环境 FastAPI 直接托管前端静态（Docker 里不用再起 nginx）
static = Path(__file__).parent.parent / "static"
if static.exists():
    app.mount("/", StaticFiles(directory=str(static), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3001, reload=True)
