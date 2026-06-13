import time
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.connection import get_db
from services.oss_storage import get_url as oss_signed_url, upload_bytes_async

router = APIRouter(prefix="/api/practice-sessions", tags=["practice-sessions"])


class CreatePracticeRequest(BaseModel):
    userId: str
    scenarioId: str


@router.post("")
async def create_practice(req: CreatePracticeRequest):
    scenario = await get_db().scenarios.find_one({"_id": req.scenarioId})
    if not scenario:
        raise HTTPException(404, "场景不存在")

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
        # 只存 OSS key，签名 URL 一律读取时现签
        "imageKey": scenario.get("imageKey", ""),
        "attempts": [],
        "createdAt": datetime.now(timezone.utc),
    }
    result = await get_db().practiceSessions.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return _sign(doc)


def _sign(practice: dict) -> dict:
    """按 imageKey / 录音 key 现生成签名 URL（1 小时有效），库里不存 URL。"""
    if practice.get("imageKey"):
        practice["imageUrl"] = oss_signed_url(practice["imageKey"])
    for rec in practice.get("recordings", []):
        if "key" in rec:
            rec["url"] = oss_signed_url(rec["key"])
    for attempt in practice.get("attempts", []):
        if attempt.get("recordingKey"):
            attempt["recordingUrl"] = oss_signed_url(attempt["recordingKey"])
    return practice


@router.get("/{pid}")
async def get_practice(pid: str):
    try:
        practice = await get_db().practiceSessions.find_one({"_id": ObjectId(pid)})
    except Exception:
        raise HTTPException(404, "练习不存在")
    if not practice:
        raise HTTPException(404, "练习不存在")
    practice["_id"] = str(practice["_id"])
    return _sign(practice)


@router.get("")
async def list_practices(userId: str = Query(...), limit: int = 20, skip: int = 0):
    cursor = get_db().practiceSessions.find({"userId": userId}).sort("createdAt", -1).skip(skip).limit(limit)
    items = []
    async for p in cursor:
        p["_id"] = str(p["_id"])
        items.append(_sign(p))
    return items


@router.post("/{practice_id}/recording")
async def upload_recording(
    practice_id: str,
    userId: str = Form(...),
    audio: UploadFile = File(...),
    attemptIndex: int = Form(-1),
):
    try:
        practice = await get_db().practiceSessions.find_one(
            {"_id": ObjectId(practice_id), "userId": userId}
        )
    except Exception:
        raise HTTPException(404, "练习不存在")
    if not practice:
        raise HTTPException(404, "练习不存在")

    data = await audio.read()
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()
    ext = "webm" if "webm" in content_type else "ogg"
    now = datetime.now(timezone.utc)
    ts = int(time.time() * 1000)
    # 路径规范参考 video-2022：资源为根、类型做子目录
    key = f"practiceSessions/{userId}/{now.strftime('%Y%m')}/{practice_id}/recording/{ts}.{ext}"

    await upload_bytes_async(key, data, content_type)
    update: dict = {"$push": {"recordings": {"key": key, "attemptIndex": attemptIndex, "createdAt": now}}}
    if 0 <= attemptIndex < len(practice.get("attempts", [])):
        update["$set"] = {f"attempts.{attemptIndex}.recordingKey": key}
    await get_db().practiceSessions.update_one({"_id": ObjectId(practice_id)}, update)
    return {"url": oss_signed_url(key)}
