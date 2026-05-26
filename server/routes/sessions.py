from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_db
from services.oss_storage import image_key, upload_from_url

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    userId: str
    topic: str
    imageUrl: str = ""


async def _archive_image(session_id: str, user_id: str, image_url: str) -> None:
    """后台任务：把图片拉到 OSS 并更新 session.ossImageUrl。失败静默忽略。"""
    try:
        key = image_key(user_id, session_id)
        oss_url = await upload_from_url(key, image_url)
        await get_db().sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"ossImageUrl": oss_url}},
        )
    except Exception:
        pass


@router.post("")
async def create_session(req: CreateSessionRequest, background_tasks: BackgroundTasks):
    doc = {
        "userId": req.userId,
        "topic": req.topic,
        "imageUrl": req.imageUrl,
        "attempts": [],
        "createdAt": datetime.now(timezone.utc),
    }
    result = await get_db().sessions.insert_one(doc)
    session_id = str(result.inserted_id)
    doc["_id"] = session_id

    if req.imageUrl:
        background_tasks.add_task(_archive_image, session_id, req.userId, req.imageUrl)

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
