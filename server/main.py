from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.connection import connect_db
from services.image_generator import init_pool
from routes import auth, generate, correct, sessions, vocabulary


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await init_pool()
    yield


app = FastAPI(title="SpeakUp API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(generate.router)
app.include_router(correct.router)
app.include_router(sessions.router)
app.include_router(vocabulary.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3001, reload=True)
