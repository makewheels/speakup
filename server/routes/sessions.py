import time
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.connection import get_db
from services.file_service import get_or_upload_from_url, orig_url
from services.oss_storage import get_url as oss_signed_url, sign_public_url, upload_bytes_async

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    userId: str
    topic: str
    imageUrl: str = ""


async def _archive_image(session_id: str, image_url: str, topic: str) -> None:
    """后台任务：把图片归档到 files 集合 + OSS，更新 session.fileId / ossImageUrl。失败静默忽略。"""
    try:
        file_doc = await get_or_upload_from_url(image_url, source="loremflickr", topic=topic)
        await get_db().sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"fileId": file_doc["_id"], "ossImageUrl": orig_url(file_doc)}},
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
        background_tasks.add_task(_archive_image, session_id, req.imageUrl, req.topic)

    return doc


def _sign_recordings(session: dict) -> dict:
    """把 recordings 里的 key 替换为临时签名 URL（1 小时有效）。"""
    for rec in session.get("recordings", []):
        if "key" in rec:
            rec["url"] = oss_signed_url(rec["key"])
    return session


def _sign_image(session: dict) -> dict:
    """把归档到私有桶的 ossImageUrl 换成签名 URL，浏览器才能直接加载。"""
    oss = session.get("ossImageUrl")
    if oss:
        session["ossImageUrl"] = sign_public_url(oss)
    return session


@router.get("/{sid}")
async def get_session(sid: str):
    try:
        session = await get_db().sessions.find_one({"_id": ObjectId(sid)})
    except Exception:
        raise HTTPException(404, "会话不存在")
    if not session:
        raise HTTPException(404, "会话不存在")
    session["_id"] = str(session["_id"])
    return _sign_image(_sign_recordings(session))


@router.get("")
async def list_sessions(userId: str = Query(...), limit: int = 20, skip: int = 0):
    cursor = get_db().sessions.find({"userId": userId}).sort("createdAt", -1).skip(skip).limit(limit)
    sessions = []
    async for s in cursor:
        s["_id"] = str(s["_id"])
        sessions.append(_sign_image(s))
    return sessions


@router.post("/{session_id}/recording")
async def upload_recording(
    session_id: str,
    userId: str = Form(...),
    audio: UploadFile = File(...),
):
    try:
        session = await get_db().sessions.find_one(
            {"_id": ObjectId(session_id), "userId": userId}
        )
    except Exception:
        raise HTTPException(404, "会话不存在")
    if not session:
        raise HTTPException(404, "会话不存在")

    data = await audio.read()
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()
    ext = "webm" if "webm" in content_type else "ogg"
    ts = int(time.time() * 1000)
    key = f"recordings/{userId}/{session_id}/{ts}.{ext}"

    await upload_bytes_async(key, data, content_type)
    now = datetime.now(timezone.utc)
    await get_db().sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$push": {"recordings": {"key": key, "createdAt": now}}},
    )
    signed = oss_signed_url(key)
    return {"url": signed}
