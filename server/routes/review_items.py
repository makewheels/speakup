from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from services.oss_storage import get_url as oss_signed_url
from utils.id_generator import review_item_id
from utils.mongo_ids import id_filter, id_values

router = APIRouter(prefix="/api/review-items", tags=["review-items"])


class AddItemsRequest(BaseModel):
    userId: str
    items: list[dict]


class ReviewRequest(BaseModel):
    remembered: bool


@router.post("")
async def add_items(req: AddItemsRequest, token_user_id: str = Depends(current_user_id)):
    assert_same_user(req.userId, token_user_id)
    now = datetime.now(timezone.utc)
    added = 0
    ids = []  # 与 req.items 顺序对应：每条返回新建或已存在的 reviewItem id，方便前端「取消收录」
    for it in req.items:
        existing = await get_db().reviewItems.find_one(
            {"userId": req.userId, "expression": it["expression"]}
        )
        if existing:
            ids.append(str(existing["_id"]))
            continue
        rid = review_item_id()
        await get_db().reviewItems.insert_one({
            "_id": rid,
            "userId": req.userId,
            "expression": it["expression"],
            "original": it.get("original", ""),
            "note": it.get("note", ""),
            "contextSentence": it.get("contextSentence", ""),
            "practiceId": it.get("practiceId", ""),
            "createdAt": now,
            "nextReviewAt": now,
            "reviewCount": 0,
            "interval": 1,
            "easiness": 2.5,
        })
        ids.append(rid)
        added += 1
    return {"added": added, "ids": ids}


@router.get("")
async def list_items(
    userId: str = Query(...),
    due: bool = False,
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    filter = {"userId": userId}
    if due:
        filter["nextReviewAt"] = {"$lte": datetime.now(timezone.utc)}
    cursor = get_db().reviewItems.find(filter).sort("nextReviewAt", 1)
    items = []
    async for item in cursor:
        item["_id"] = str(item["_id"])
        items.append(item)

    # 关联练习补场景图（imageKey 现签）+ topic，供复习卡展示与原题重练
    practice_ids = {}
    for pid in {i.get("practiceId") for i in items if i.get("practiceId")}:
        for value in id_values(pid):
            practice_ids[value] = pid
    scenes = {}
    if practice_ids:
        async for p in get_db().practiceSessions.find(
            {"_id": {"$in": list(practice_ids)}},
            {"imageKey": 1, "topic": 1},
        ):
            key = p.get("imageKey", "")
            scenes[practice_ids[p["_id"]]] = {
                "image": oss_signed_url(key) if key else "",
                "topic": p.get("topic", ""),
            }
    for i in items:
        sc = scenes.get(i.get("practiceId"))
        i["sceneImageUrl"] = sc["image"] if sc else ""
        i["topic"] = sc["topic"] if sc else ""
    return items


@router.post("/{rid}/review")
async def review_item(
    rid: str,
    req: ReviewRequest,
    userId: str = Query(...),
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    item = await get_db().reviewItems.find_one({**id_filter(rid), "userId": token_user_id})
    if not item:
        raise HTTPException(404, "复习项不存在")

    item["reviewCount"] += 1
    if req.remembered:
        item["easiness"] = min(3.0, item["easiness"] + 0.1)
        item["interval"] = round(item["interval"] * item["easiness"])
    else:
        item["easiness"] = max(1.3, item["easiness"] - 0.3)
        item["interval"] = 1

    item["nextReviewAt"] = datetime.now(timezone.utc) + timedelta(days=item["interval"])
    await get_db().reviewItems.update_one(
        id_filter(rid),
        {"$set": {
            "reviewCount": item["reviewCount"],
            "easiness": item["easiness"],
            "interval": item["interval"],
            "nextReviewAt": item["nextReviewAt"],
        }},
    )
    item["_id"] = str(item["_id"])
    return item


@router.delete("/{rid}")
async def delete_item(
    rid: str,
    userId: str = Query(...),
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    result = await get_db().reviewItems.delete_one({**id_filter(rid), "userId": token_user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "复习项不存在")
    return {"ok": True}
