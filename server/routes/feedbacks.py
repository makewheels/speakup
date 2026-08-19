from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo import ReturnDocument

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from utils.data_source import normalize_source_type
from utils.id_generator import feedback_id
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/feedbacks", tags=["feedbacks"])

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
    attemptIndex: int | None = None
    # 前端带的 AI 反馈快照（{score, summary, nativeVersion, gaps, transcript, round}），
    # 排查"反馈不好用"时直接还原当时 AI 说了啥，不依赖 attempt 还在
    snapshot: dict | None = None


@router.post("")
async def submit_feedback(req: FeedbackRequest, token_user_id: str = Depends(current_user_id)):
    valid_tags = PRACTICE_TAGS if req.type == "practice" else GENERAL_TAGS
    tags = [t for t in (req.tags or []) if t in valid_tags]
    comment = (req.comment or "").strip()

    if req.type == "practice":
        if not req.practiceId:
            raise HTTPException(400, "练习反馈需要 practiceId")
        practice = await get_db().practiceSessions.find_one(
            {**id_filter(req.practiceId), "userId": token_user_id}
        )
        if not practice:
            raise HTTPException(404, "练习不存在")
        source_type = normalize_source_type(practice.get("sourceType"))
        # 一个 attempt 只一条反馈：同一 userId+practiceId+attemptIndex 存在则更新，不存在才新建。
        # 这样下次打开这一轮能看到上次反馈并修改（覆盖更新，不保留历史）。
        now = datetime.now(timezone.utc)
        doc = await get_db().feedbacks.find_one_and_update(
            {"userId": token_user_id, "practiceId": req.practiceId, "attemptIndex": req.attemptIndex},
            {
                "$set": {
                    "type": "practice",
                    "rating": req.rating,
                    "tags": tags,
                    "comment": comment,
                    "scenarioId": practice.get("scenarioId", ""),
                    "scenarioTitle": practice.get("title", ""),
                    "snapshot": req.snapshot or {},
                    "sourceType": source_type,
                    "updatedAt": now,
                },
                "$setOnInsert": {
                    "_id": feedback_id(),
                    "userId": token_user_id,
                    "practiceId": req.practiceId,
                    "attemptIndex": req.attemptIndex,
                    "createdAt": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        # 清理同 attempt 的历史重复条（早期 insert_one 可能产生多条），保证一个 attempt 一条
        await get_db().feedbacks.delete_many({
            "userId": token_user_id,
            "practiceId": req.practiceId,
            "attemptIndex": req.attemptIndex,
            "_id": {"$ne": doc["_id"]},
        })
        doc["_id"] = str(doc["_id"])
        return doc

    # general 反馈不按 attempt 去重，每次新建一条
    user = await get_db().users.find_one(id_filter(token_user_id), {"sourceType": 1})
    doc = {
        "_id": feedback_id(),
        "userId": token_user_id,
        "sourceType": normalize_source_type((user or {}).get("sourceType")),
        "type": "general",
        "rating": req.rating,
        "tags": tags,
        "comment": comment,
        "createdAt": datetime.now(timezone.utc),
    }
    await get_db().feedbacks.insert_one(doc)
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_my_feedbacks(
    userId: str = Query(...),
    practiceId: str | None = Query(None),
    attemptIndex: int | None = Query(None),
    token_user_id: str = Depends(current_user_id),
):
    """当前用户自查反馈。带 practiceId+attemptIndex 时精确取某一轮的练习反馈（0 或 1 条）。"""
    assert_same_user(userId, token_user_id)
    query = {"userId": token_user_id}
    if practiceId is not None:
        query["practiceId"] = practiceId
        if attemptIndex is not None:
            query["attemptIndex"] = attemptIndex
    items = []
    async for f in get_db().feedbacks.find(query).sort([("updatedAt", -1), ("createdAt", -1)]):
        f["_id"] = str(f["_id"])
        items.append(f)
    return items
