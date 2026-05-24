from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId
from db.connection import get_db

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    userId: str
    topic: str
    imageUrl: str = ""


@router.post("")
async def create_session(req: CreateSessionRequest):
    doc = {
        "userId": req.userId,
        "topic": req.topic,
        "imageUrl": req.imageUrl,
        "attempts": [],
        "createdAt": datetime.now(timezone.utc),
    }
    result = await get_db().sessions.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/{sid}")
async def get_session(sid: str):
    try:
        session = await get_db().sessions.find_one({"_id": ObjectId(sid)})
    except Exception:
        raise HTTPException(404, "会话不存在")
    if not session:
        raise HTTPException(404, "会话不存在")
    session["_id"] = str(session["_id"])
    return session


@router.get("/")
async def list_sessions(userId: str = Query(...), limit: int = 20, skip: int = 0):
    cursor = get_db().sessions.find({"userId": userId}).sort("createdAt", -1).skip(skip).limit(limit)
    sessions = []
    async for s in cursor:
        s["_id"] = str(s["_id"])
        sessions.append(s)
    return sessions
