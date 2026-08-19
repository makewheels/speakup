from fastapi import APIRouter, Depends, HTTPException, Query

from services.auth_tokens import assert_same_user, current_user_id
from services.free_practice import next_free_topic

router = APIRouter(prefix="/api/free-topics", tags=["free-topics"])


@router.get("/next")
async def next_topic(
    userId: str = Query(...),
    token_user_id: str = Depends(current_user_id),
):
    """抽一个该用户没说过的自由说话题；池子用完自动调 LLM 补一批。"""
    assert_same_user(userId, token_user_id)
    doc = await next_free_topic(token_user_id)
    if not doc:
        raise HTTPException(404, "暂无可用话题，请稍后再试")
    return {"_id": str(doc["_id"]), "text": doc.get("text", ""), "zh": doc.get("zh", "")}
