import secrets
import string
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from services.oss_storage import get_url as oss_signed_url, upload_bytes_async
from utils.data_source import normalize_source_type
from utils.id_generator import practice_session_id
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/practice-sessions", tags=["practice-sessions"])
# 公开分享读取（无鉴权），独立前缀
share_router = APIRouter(prefix="/api/share", tags=["share"])

# 分享 token：纯字母数字（无 - / _ 等特殊字符），12 位 ≈ 62^12 碰撞概率可忽略
_TOKEN_ALPHABET = string.ascii_letters + string.digits


def _gen_token(n: int = 12) -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(n))


async def _gen_unique_token() -> str:
    """生成库内不重复的 token（兜底校验，正常一次命中）。"""
    while True:
        token = _gen_token()
        if not await get_db().practiceSessions.find_one({"shareToken": token}):
            return token


class CreatePracticeRequest(BaseModel):
    userId: str
    scenarioId: str


@router.post("")
async def create_practice(req: CreatePracticeRequest, token_user_id: str = Depends(current_user_id)):
    assert_same_user(req.userId, token_user_id)
    scenario = await get_db().scenarios.find_one({"_id": req.scenarioId})
    if not scenario:
        raise HTTPException(404, "场景不存在")
    user = await get_db().users.find_one(id_filter(token_user_id), {"sourceType": 1})
    source_type = normalize_source_type((user or {}).get("sourceType"))

    doc = {
        "_id": practice_session_id(),
        "userId": req.userId,
        "sourceType": source_type,
        "scenarioId": req.scenarioId,
        "kind": scenario.get("kind", "task"),
        "title": scenario.get("title", ""),       # 历史列表标题用
        "topic": scenario.get("where", ""),
        # 场景快照：题目以后改了也不影响历史回看
        "scenario": {
            "kind": scenario.get("kind", "task"),
            "title": scenario.get("title", ""),
            "where": scenario.get("where", ""),
            "story": scenario.get("story", ""),
            "mission": scenario.get("mission", ""),
            "points": scenario.get("points", []),
            "targetWords": scenario.get("targetWords", []),
        },
        # 只存 OSS key，签名 URL 一律读取时现签
        "imageKey": scenario.get("imageKey", ""),
        "videoKey": scenario.get("videoKey", ""),
        "attempts": [],
        "createdAt": datetime.now(timezone.utc),
    }
    await get_db().practiceSessions.insert_one(doc)
    return _sign(doc)


def _sign(practice: dict) -> dict:
    """按 imageKey / 录音 key 现生成签名 URL（1 小时有效），库里不存 URL。"""
    if practice.get("imageKey"):
        practice["imageUrl"] = oss_signed_url(practice["imageKey"])
    if practice.get("videoKey"):
        practice["videoUrl"] = oss_signed_url(practice["videoKey"])
    for rec in practice.get("recordings", []):
        if "key" in rec:
            rec["url"] = oss_signed_url(rec["key"])
    for attempt in practice.get("attempts", []):
        if attempt.get("recordingKey"):
            attempt["recordingUrl"] = oss_signed_url(attempt["recordingKey"])
    return practice


@router.get("/{pid}")
async def get_practice(pid: str, token_user_id: str = Depends(current_user_id)):
    practice = await get_db().practiceSessions.find_one({**id_filter(pid), "userId": token_user_id})
    if not practice:
        raise HTTPException(404, "练习不存在")
    practice["_id"] = str(practice["_id"])
    return _sign(practice)


@router.get("")
async def list_practices(
    userId: str = Query(...),
    limit: int = 20,
    skip: int = 0,
    sharedOnly: bool = False,
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    # 只返回真正开口评估过的（attempts 非空）；看了图没说的空记录不进历史，
    # 否则前端二次过滤会出现"拉了一页全被滤光、要点很多次 load more"。
    query = {"userId": userId, "attempts.0": {"$exists": True}}
    if sharedOnly:
        query["shared"] = True
    cursor = get_db().practiceSessions.find(query).sort("createdAt", -1).skip(skip).limit(limit)
    items = []
    async for p in cursor:
        p["_id"] = str(p["_id"])
        items.append(_sign(p))
    return items


class ShareRequest(BaseModel):
    userId: str


@router.post("/{pid}/share")
async def share_practice(pid: str, req: ShareRequest, token_user_id: str = Depends(current_user_id)):
    """开启分享：生成随机 token（已有则复用）。幂等。"""
    assert_same_user(req.userId, token_user_id)
    practice = await get_db().practiceSessions.find_one({**id_filter(pid), "userId": token_user_id})
    if not practice:
        raise HTTPException(404, "练习不存在")

    token = practice.get("shareToken") or await _gen_unique_token()
    await get_db().practiceSessions.update_one(
        id_filter(pid),
        {"$set": {"shareToken": token, "shared": True, "sharedAt": datetime.now(timezone.utc)}},
    )
    return {"shareToken": token}


@router.delete("/{pid}/share")
async def unshare_practice(
    pid: str,
    userId: str = Query(...),
    token_user_id: str = Depends(current_user_id),
):
    """取消分享：只置 shared=False，保留 token。再次开启即复用同一链接（旧链接复活）。"""
    assert_same_user(userId, token_user_id)
    result = await get_db().practiceSessions.update_one(
        {**id_filter(pid), "userId": token_user_id},
        {"$set": {"shared": False}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "练习不存在")
    return {"ok": True}


@share_router.get("/{token}")
async def get_shared_practice(token: str):
    """公开读取：凭 shareToken 返回完整练习 + 分享者昵称。无鉴权。"""
    practice = await get_db().practiceSessions.find_one({"shareToken": token, "shared": True})
    if not practice:
        raise HTTPException(404, "分享已关闭或不存在")
    practice["_id"] = str(practice["_id"])
    owner = await get_db().users.find_one(id_filter(practice["userId"]))
    practice["ownerNickname"] = (owner or {}).get("nickname", "")
    return _sign(practice)


@router.post("/{practice_id}/recording")
async def upload_recording(
    practice_id: str,
    userId: str = Form(...),
    audio: UploadFile = File(...),
    attemptIndex: int = Form(-1),
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    practice = await get_db().practiceSessions.find_one(
        {**id_filter(practice_id), "userId": token_user_id}
    )
    if not practice:
        raise HTTPException(404, "练习不存在")

    data = await audio.read()
    content_type = (audio.content_type or "audio/webm").split(";")[0].strip()
    ext = "webm" if "webm" in content_type else "ogg"
    now = datetime.now(timezone.utc)
    ts = int(time.time() * 1000)
    # 路径规范参考 video-2022：资源为根、类型做子目录
    key = f"practiceSessions/{token_user_id}/{now.strftime('%Y%m')}/{practice_id}/recording/{ts}.{ext}"

    await upload_bytes_async(key, data, content_type)
    update: dict = {"$push": {"recordings": {"key": key, "attemptIndex": attemptIndex, "createdAt": now}}}
    if 0 <= attemptIndex < len(practice.get("attempts", [])):
        update["$set"] = {f"attempts.{attemptIndex}.recordingKey": key}
    await get_db().practiceSessions.update_one(id_filter(practice_id), update)
    return {"url": oss_signed_url(key)}
