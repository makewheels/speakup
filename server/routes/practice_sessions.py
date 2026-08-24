import secrets
import string
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from services.oss_storage import (
    delete_async,
    get_url as oss_signed_url,
    upload_bytes_async,
)
from services.practice_attempts import hydrate_practice, resolve_attempt, update_attempt
from services.storage_paths import PracticeAssetContext, recording_original_key
from utils.data_source import normalize_source_type
from utils.id_generator import practice_session_id, recording_id
from utils.mongo_ids import id_filter, id_values

router = APIRouter(prefix="/api/practice-sessions", tags=["practice-sessions"])
# 公开分享读取（无鉴权），独立前缀
share_router = APIRouter(prefix="/api/share", tags=["share"])
logger = logging.getLogger(__name__)

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
    scenarioId: str = ""          # 场景题必填；自由说留空
    mode: str = "scenario"        # scenario 场景题 / free 自由说（历史缺省按场景题）
    freeTopicId: str = ""         # 自由说话题 id（无话题自由说为空）
    freeTopic: str = ""           # 自由说话题文本快照（无话题自由说为空）


class RecordingTarget:
    def __init__(
        self,
        userId: str = Form(...),
        attemptId: str = Form(""),
        attemptIndex: int = Form(-1),
    ):
        self.user_id = userId
        self.attempt_id = attemptId
        self.attempt_index = attemptIndex


@router.post("")
async def create_practice(req: CreatePracticeRequest, token_user_id: str = Depends(current_user_id)):
    assert_same_user(req.userId, token_user_id)
    user = await get_db().users.find_one(id_filter(token_user_id), {"sourceType": 1})
    source_type = normalize_source_type((user or {}).get("sourceType"))

    if req.mode == "free":
        doc = _build_free_doc(req, source_type)
    else:
        scenario = await get_db().scenarios.find_one({"_id": req.scenarioId})
        if not scenario:
            raise HTTPException(404, "场景不存在")
        doc = _build_scenario_doc(req, scenario, source_type)
    await get_db().practiceSessions.insert_one(doc)
    return _sign({**doc, "attempts": []})


def _build_free_doc(req: CreatePracticeRequest, source_type: str) -> dict:
    """自由说会话：无场景，快照里带 kind=free + 话题（可空），corrector 据此走自由说反馈。"""
    topic = (req.freeTopic or "").strip()
    title = topic or "自由说"      # 历史列表标题用
    return {
        "_id": practice_session_id(),
        "userId": req.userId,
        "sourceType": source_type,
        "mode": "free",
        "freeTopicId": req.freeTopicId or "",
        "freeTopic": topic,
        "scenarioId": "",
        "kind": "free",
        "title": title,
        "topic": "",
        "scenario": {
            "kind": "free",
            "title": title,
            "freeTopic": topic,
            "where": "",
            "story": "",
            "mission": "",
            "points": [],
            "targetWords": [],
        },
        "imageKey": "",
        "videoKey": "",
        "attemptSeq": 0,
        "createdAt": datetime.now(timezone.utc),
    }


def _build_scenario_doc(req: CreatePracticeRequest, scenario: dict, source_type: str) -> dict:
    return {
        "_id": practice_session_id(),
        "userId": req.userId,
        "sourceType": source_type,
        "mode": "scenario",
        "freeTopicId": "",
        "freeTopic": "",
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
        "attemptSeq": 0,
        "createdAt": datetime.now(timezone.utc),
    }


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
        key = _recording_key(attempt)
        if key:
            attempt["recordingUrl"] = oss_signed_url(key)
    return practice


def _recording_key(attempt: dict) -> str:
    """读取新结构，兼容迁移前的扁平 recordingKey。"""
    return (attempt.get("recording") or {}).get("key") or attempt.get("recordingKey") or ""


@router.get("/{pid}")
async def get_practice(pid: str, token_user_id: str = Depends(current_user_id)):
    practice = await get_db().practiceSessions.find_one({**id_filter(pid), "userId": token_user_id})
    if not practice:
        raise HTTPException(404, "练习不存在")
    return _sign(await hydrate_practice(practice))


@router.get("")
async def list_practices(
    userId: str = Query(...),
    limit: int = 20,
    skip: int = 0,
    sharedOnly: bool = False,
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    # Completed Attempts live in their own collection. Keep embedded lookup for
    # the deployment window until the production migration removes it.
    attempt_practice_ids = await get_db().practiceAttempts.distinct(
        "practiceId", {"userId": userId, "status": "completed"}
    )
    practice_id_values = [
        value
        for practice_id in attempt_practice_ids
        for value in id_values(str(practice_id))
    ]
    query = {
        "userId": userId,
        "$or": [
            {"attempts.0": {"$exists": True}},
            {"_id": {"$in": practice_id_values}},
        ],
    }
    if sharedOnly:
        query["shared"] = True
    cursor = get_db().practiceSessions.find(query).sort("createdAt", -1).skip(skip).limit(limit)
    items = []
    async for p in cursor:
        items.append(_sign(await hydrate_practice(p)))
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
    practice = await hydrate_practice(practice)
    owner = await get_db().users.find_one(id_filter(practice["userId"]))
    practice["ownerNickname"] = (owner or {}).get("nickname", "")
    return _sign(practice)


@router.post("/{practice_id}/recording")
async def upload_recording(
    practice_id: str,
    audio: UploadFile = File(...),
    target: RecordingTarget = Depends(),
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(target.user_id, token_user_id)
    practice = await get_db().practiceSessions.find_one(
        {**id_filter(practice_id), "userId": token_user_id}
    )
    if not practice:
        raise HTTPException(404, "练习不存在")
    attempt = await resolve_attempt(
        practice,
        attempt_id=target.attempt_id,
        attempt_index=target.attempt_index,
    )
    if not attempt:
        raise HTTPException(409, "请先完成本轮反馈，再上传对应录音")
    resolved_attempt_id = attempt["attemptId"]
    legacy_index = int(attempt.get("round") or 1) - 1

    data = await audio.read()
    if not data:
        raise HTTPException(400, "录音文件不能为空")
    mime_type = audio.content_type or "audio/webm"
    content_type = mime_type.split(";")[0].strip()
    extension_by_type = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/wav": "wav",
        "audio/mpeg": "mp3",
    }
    ext = extension_by_type.get(content_type, "webm")
    now = datetime.now(timezone.utc)
    asset_id = recording_id()
    context = PracticeAssetContext(
        user_id=token_user_id,
        created_at=practice.get("createdAt") or now,
        practice_id=practice_id,
        attempt_id=resolved_attempt_id,
    )
    key = recording_original_key(context, asset_id, ext)
    recording = {
        "id": asset_id,
        "key": key,
        "format": ext,
        "contentType": mime_type,
        "sizeBytes": len(data),
        "createdAt": now,
    }

    await upload_bytes_async(key, data, content_type)
    try:
        updated = await update_attempt(
            resolved_attempt_id,
            {"$set": {"recording": recording}, "$unset": {"recordingKey": ""}},
        )
        if not updated:
            await get_db().practiceSessions.update_one(
                id_filter(practice_id),
                {
                    "$set": {f"attempts.{legacy_index}.recording": recording},
                    "$unset": {f"attempts.{legacy_index}.recordingKey": ""},
                    "$pull": {"recordings": {"attemptIndex": legacy_index}},
                },
            )
    except Exception:
        try:
            await delete_async(key)
        except Exception:
            logger.warning("未入库录音 OSS 对象清理失败: practice=%s key=%s", practice_id, key, exc_info=True)
        raise
    old_key = _recording_key(attempt)
    if old_key and old_key != key:
        try:
            await delete_async(old_key)
        except Exception:
            logger.warning("旧录音 OSS 对象清理失败: practice=%s key=%s", practice_id, old_key, exc_info=True)
    return {
        "recording": recording,
        "url": oss_signed_url(key),
        "attemptId": resolved_attempt_id,
        "pronunciationEnabled": False,
    }


@router.api_route(
    "/{practice_id}/attempts/{attempt_ref}/pronunciation{suffix:path}",
    methods=["GET", "POST"],
)
async def pronunciation_removed(practice_id: str, attempt_ref: str, suffix: str = ""):
    """The broken pronunciation experience is intentionally disabled."""
    raise HTTPException(410, "发音评测已暂时下线")


@share_router.get("/{token}/attempts/{attempt_ref}/pronunciation{suffix:path}")
async def shared_pronunciation_removed(token: str, attempt_ref: str, suffix: str = ""):
    raise HTTPException(410, "发音评测已暂时下线")
