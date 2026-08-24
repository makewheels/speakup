import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ValidationError
from pymongo import ReturnDocument

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from services.feedback_images import (
    MAX_FEEDBACK_IMAGE_BYTES,
    MAX_FEEDBACK_IMAGES,
    InvalidFeedbackImage,
    detect_feedback_image,
    safe_feedback_filename,
)
from services.oss_storage import delete_async, get_url as oss_signed_url, upload_bytes_async
from services.practice_attempts import resolve_attempt
from services.storage_paths import feedback_image_key
from utils.data_source import normalize_source_type
from utils.id_generator import feedback_id, feedback_image_id
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/feedbacks", tags=["feedbacks"])
logger = logging.getLogger(__name__)

# 结果页反馈（踩时）可选原因标签，对应反馈页各区块
PRACTICE_TAGS = {
    "score_too_strict", "score_too_loose",
    "gap_wrong", "native_unnatural", "transcript_wrong", "summary_bad",
}
# 全局反馈标签
GENERAL_TAGS = {"product", "scenario", "asr", "bug", "other"}


class FeedbackRequest(BaseModel):
    type: Literal["practice", "general"]
    rating: Literal["good", "bad"] | None = None
    tags: list[str] = []
    comment: str = ""
    practiceId: str | None = None
    attemptId: str | None = None
    attemptIndex: int | None = None
    # 前端带的 AI 反馈快照（{score, summary, gaps, transcript, round}），
    # 排查"反馈不好用"时直接还原当时 AI 说了啥，不依赖 attempt 还在
    snapshot: dict | None = None


def _signed(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    for image in doc.get("images", []):
        if image.get("key"):
            image["url"] = oss_signed_url(image["key"])
    return doc


async def _save_feedback(
    req: FeedbackRequest,
    token_user_id: str,
    *,
    doc_id: str | None = None,
    new_images: list[dict] | None = None,
) -> dict:
    valid_tags = PRACTICE_TAGS if req.type == "practice" else GENERAL_TAGS
    tags = [t for t in (req.tags or []) if t in valid_tags]
    comment = (req.comment or "").strip()
    images = new_images or []

    if req.type == "practice":
        if not req.practiceId:
            raise HTTPException(400, "练习反馈需要 practiceId")
        practice = await get_db().practiceSessions.find_one(
            {**id_filter(req.practiceId), "userId": token_user_id}
        )
        if not practice:
            raise HTTPException(404, "练习不存在")
        attempt = await resolve_attempt(
            practice,
            attempt_id=req.attemptId or "",
            attempt_index=req.attemptIndex if req.attemptIndex is not None else -1,
        )
        if not attempt:
            raise HTTPException(404, "练习尝试不存在")
        attempt_id = attempt["attemptId"]
        attempt_index = int(attempt.get("round") or 1) - 1
        source_type = normalize_source_type(practice.get("sourceType"))
        # 一个 Attempt 只一条反馈；attemptIndex 仅用于命中迁移前的历史反馈。
        # 这样下次打开这一轮能看到上次反馈并修改（覆盖更新，不保留历史）。
        now = datetime.now(timezone.utc)
        update: dict = {
            "$set": {
                "type": "practice",
                "rating": req.rating,
                "tags": tags,
                "comment": comment,
                "scenarioId": practice.get("scenarioId", ""),
                "scenarioTitle": practice.get("title", ""),
                "snapshot": req.snapshot or {},
                "sourceType": source_type,
                "attemptId": attempt_id,
                "attemptIndex": attempt_index,
                "updatedAt": now,
            },
            "$setOnInsert": {
                "_id": doc_id or feedback_id(),
                "userId": token_user_id,
                "practiceId": req.practiceId,
                "createdAt": now,
            },
        }
        if images:
            update["$push"] = {"images": {"$each": images}}
        lookup = {
            "userId": token_user_id,
            "practiceId": req.practiceId,
            "$or": [
                {"attemptId": attempt_id},
                {"attemptId": {"$exists": False}, "attemptIndex": attempt_index},
            ],
        }
        doc = await get_db().feedbacks.find_one_and_update(
            lookup,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        # 清理同 attempt 的历史重复条（早期 insert_one 可能产生多条），保证一个 attempt 一条
        await get_db().feedbacks.delete_many({
            "userId": token_user_id,
            "practiceId": req.practiceId,
            "$or": [
                {"attemptId": attempt_id},
                {"attemptId": {"$exists": False}, "attemptIndex": attempt_index},
            ],
            "_id": {"$ne": doc["_id"]},
        })
        return _signed(doc)

    # general 反馈不按 attempt 去重，每次新建一条
    user = await get_db().users.find_one(id_filter(token_user_id), {"sourceType": 1})
    doc = {
        "_id": doc_id or feedback_id(),
        "userId": token_user_id,
        "sourceType": normalize_source_type((user or {}).get("sourceType")),
        "type": "general",
        "rating": req.rating,
        "tags": tags,
        "comment": comment,
        "images": images,
        "createdAt": datetime.now(timezone.utc),
    }
    await get_db().feedbacks.insert_one(doc)
    return _signed(doc)


@router.post("")
async def submit_feedback(req: FeedbackRequest, token_user_id: str = Depends(current_user_id)):
    return await _save_feedback(req, token_user_id)


async def _delete_uploaded(keys: list[str], token_user_id: str) -> None:
    prefix = f"feedbacks/{token_user_id}/"
    for key in keys:
        if not key.startswith(prefix):
            continue
        try:
            await delete_async(key)
        except Exception:
            logger.warning("未入库反馈图片清理失败: key=%s", key, exc_info=True)


async def _existing_feedback_for_upload(req: FeedbackRequest, token_user_id: str) -> dict | None:
    if req.type != "practice":
        user = await get_db().users.find_one(id_filter(token_user_id), {"_id": 1})
        if not user:
            raise HTTPException(404, "用户不存在")
        return None
    if not req.practiceId:
        raise HTTPException(400, "练习反馈需要 practiceId")
    practice = await get_db().practiceSessions.find_one(
        {**id_filter(req.practiceId), "userId": token_user_id}
    )
    if not practice:
        raise HTTPException(404, "练习不存在")
    attempt = await resolve_attempt(
        practice,
        attempt_id=req.attemptId or "",
        attempt_index=req.attemptIndex if req.attemptIndex is not None else -1,
    )
    if not attempt:
        raise HTTPException(404, "练习尝试不存在")
    attempt_id = attempt["attemptId"]
    attempt_index = int(attempt.get("round") or 1) - 1
    return await get_db().feedbacks.find_one({
        "userId": token_user_id,
        "practiceId": req.practiceId,
        "$or": [
            {"attemptId": attempt_id},
            {"attemptId": {"$exists": False}, "attemptIndex": attempt_index},
        ],
    })


async def _upload_feedback_images(
    images: list[UploadFile],
    token_user_id: str,
    target_id: str,
    created_at: datetime,
    now: datetime,
) -> list[dict]:
    assets: list[dict] = []
    uploaded_keys: list[str] = []
    try:
        for upload in images:
            data = await upload.read(MAX_FEEDBACK_IMAGE_BYTES + 1)
            if not data:
                raise HTTPException(400, "反馈图片不能为空")
            if len(data) > MAX_FEEDBACK_IMAGE_BYTES:
                raise HTTPException(413, "单张反馈图片不能超过 30 MB")
            content_type, extension = detect_feedback_image(data)
            image_id = feedback_image_id()
            key = feedback_image_key(token_user_id, created_at, target_id, image_id, extension)
            await upload_bytes_async(key, data, content_type)
            uploaded_keys.append(key)
            assets.append({
                "id": image_id,
                "key": key,
                "fileName": safe_feedback_filename(upload.filename, extension),
                "contentType": content_type,
                "sizeBytes": len(data),
                "createdAt": now,
            })
    except InvalidFeedbackImage as exc:
        await _delete_uploaded(uploaded_keys, token_user_id)
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        await _delete_uploaded(uploaded_keys, token_user_id)
        raise
    return assets


@router.post("/with-images")
async def submit_feedback_with_images(
    payload: str = Form(...),
    images: list[UploadFile] = File(...),
    token_user_id: str = Depends(current_user_id),
):
    try:
        req = FeedbackRequest.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(422, "反馈数据格式无效") from exc
    if not 1 <= len(images) <= MAX_FEEDBACK_IMAGES:
        raise HTTPException(400, f"每条反馈最多上传 {MAX_FEEDBACK_IMAGES} 张图片")

    existing = await _existing_feedback_for_upload(req, token_user_id)

    existing_count = len((existing or {}).get("images", []))
    if existing_count + len(images) > MAX_FEEDBACK_IMAGES:
        raise HTTPException(400, f"每条反馈最多保留 {MAX_FEEDBACK_IMAGES} 张图片")

    now = datetime.now(timezone.utc)
    target_id = str((existing or {}).get("_id") or feedback_id())
    created_at = (existing or {}).get("createdAt") or now
    assets = await _upload_feedback_images(images, token_user_id, target_id, created_at, now)
    try:
        return await _save_feedback(req, token_user_id, doc_id=target_id, new_images=assets)
    except Exception:
        await _delete_uploaded([asset["key"] for asset in assets], token_user_id)
        raise


@router.get("")
async def list_my_feedbacks(
    userId: str = Query(...),
    practiceId: str | None = Query(None),
    attemptId: str | None = Query(None),
    attemptIndex: int | None = Query(None),
    token_user_id: str = Depends(current_user_id),
):
    """当前用户自查反馈。带 practiceId+attemptIndex 时精确取某一轮的练习反馈（0 或 1 条）。"""
    assert_same_user(userId, token_user_id)
    query = {"userId": token_user_id}
    if practiceId is not None:
        query["practiceId"] = practiceId
        resolved_index = attemptIndex
        if attemptId:
            practice = await get_db().practiceSessions.find_one(
                {**id_filter(practiceId), "userId": token_user_id}
            )
            attempt = await resolve_attempt(practice or {}, attempt_id=attemptId) if practice else None
            if attempt:
                resolved_index = int(attempt.get("round") or 1) - 1
            query["$or"] = [
                {"attemptId": attemptId},
                {"attemptId": {"$exists": False}, "attemptIndex": resolved_index},
            ]
        elif resolved_index is not None:
            query["attemptIndex"] = resolved_index
    items = []
    async for f in get_db().feedbacks.find(query).sort([("updatedAt", -1), ("createdAt", -1)]):
        items.append(_signed(f))
    return items
