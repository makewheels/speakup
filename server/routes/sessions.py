import time
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.connection import get_db
from services.oss_storage import get_url as oss_signed_url, sign_public_url, upload_bytes_async

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    userId: str
    scenarioId: str


@router.post("")
async def create_session(req: CreateSessionRequest):
    scenario = await get_db().scenarios.find_one({"_id": req.scenarioId})
    if not scenario:
        raise HTTPException(404, "场景不存在")

    file_doc = await get_db().files.find_one({"_id": scenario.get("imageFileId", "")})
    oss_image_url = file_doc["variants"]["orig"]["url"] if file_doc else ""

    doc = {
        "userId": req.userId,
        "scenarioId": req.scenarioId,
        "topic": scenario.get("where", ""),
        # 场景快照：题目以后改了也不影响历史回看
        "scenario": {
            "where": scenario.get("where", ""),
            "story": scenario.get("story", ""),
            "mission": scenario.get("mission", ""),
            "targetWords": scenario.get("targetWords", []),
        },
        "fileId": scenario.get("imageFileId", ""),
        "ossImageUrl": oss_image_url,
        "attempts": [],
        "createdAt": datetime.now(timezone.utc),
    }
    result = await get_db().sessions.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return _sign_image(doc)


def _sign_recordings(session: dict) -> dict:
    """把 recordings 里的 key 替换为临时签名 URL（1 小时有效）。"""
    for rec in session.get("recordings", []):
        if "key" in rec:
            rec["url"] = oss_signed_url(rec["key"])
    for attempt in session.get("attempts", []):
        if attempt.get("recordingKey"):
            attempt["recordingUrl"] = oss_signed_url(attempt["recordingKey"])
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
    attemptIndex: int = Form(-1),
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
    now = datetime.now(timezone.utc)
    ts = int(time.time() * 1000)
    # 路径规范参考 video-2022：{资源根}/{userId}/{yyyyMM}/{sessionId}/{ts}.{ext}
    key = f"recordings/{userId}/{now.strftime('%Y%m')}/{session_id}/{ts}.{ext}"

    await upload_bytes_async(key, data, content_type)
    update: dict = {"$push": {"recordings": {"key": key, "attemptIndex": attemptIndex, "createdAt": now}}}
    if 0 <= attemptIndex < len(session.get("attempts", [])):
        update["$set"] = {f"attempts.{attemptIndex}.recordingKey": key}
    await get_db().sessions.update_one({"_id": ObjectId(session_id)}, update)
    return {"url": oss_signed_url(key)}
