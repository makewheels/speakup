from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
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

    doc = {
        "_id": feedback_id(),
        "userId": token_user_id,
        "type": req.type,
        "rating": req.rating,
        "tags": tags,
        "comment": (req.comment or "").strip(),
        "createdAt": datetime.now(timezone.utc),
    }

    if req.type == "practice":
        if not req.practiceId:
            raise HTTPException(400, "练习反馈需要 practiceId")
        practice = await get_db().practiceSessions.find_one(
            {**id_filter(req.practiceId), "userId": token_user_id}
        )
        if not practice:
            raise HTTPException(404, "练习不存在")
        doc["practiceId"] = req.practiceId
        doc["attemptIndex"] = req.attemptIndex
        doc["scenarioId"] = practice.get("scenarioId", "")
        doc["scenarioTitle"] = practice.get("title", "")
        doc["snapshot"] = req.snapshot or {}

    await get_db().feedbacks.insert_one(doc)
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_my_feedbacks(
    userId: str = Query(...),
    token_user_id: str = Depends(current_user_id),
):
    """当前用户自查自己提过的反馈。产品方查全量用 scripts/export_feedbacks.py。"""
    assert_same_user(userId, token_user_id)
    items = []
    async for f in get_db().feedbacks.find({"userId": token_user_id}).sort("createdAt", -1):
        f["_id"] = str(f["_id"])
        items.append(f)
    return items
