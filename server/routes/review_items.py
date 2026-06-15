from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId
from db.connection import get_db
from services.oss_storage import get_url as oss_signed_url

router = APIRouter(prefix="/api/review-items", tags=["review-items"])


class AddItemsRequest(BaseModel):
    userId: str
    items: list[dict]


class ReviewRequest(BaseModel):
    remembered: bool


@router.post("")
async def add_items(req: AddItemsRequest):
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
        res = await get_db().reviewItems.insert_one({
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
        ids.append(str(res.inserted_id))
        added += 1
    return {"added": added, "ids": ids}


@router.get("")
async def list_items(userId: str = Query(...), due: bool = False):
    filter = {"userId": userId}
    if due:
        filter["nextReviewAt"] = {"$lte": datetime.now(timezone.utc)}
    cursor = get_db().reviewItems.find(filter).sort("nextReviewAt", 1)
    items = []
    async for item in cursor:
        item["_id"] = str(item["_id"])
        items.append(item)

    # 关联练习补场景图（imageKey 现签）+ topic，供复习卡展示与原题重练
    oid_map = {}
    for pid in {i.get("practiceId") for i in items if i.get("practiceId")}:
        try:
            oid_map[ObjectId(pid)] = pid
        except Exception:
            pass
    scenes = {}
    if oid_map:
        async for p in get_db().practiceSessions.find(
            {"_id": {"$in": list(oid_map)}},
            {"imageKey": 1, "topic": 1},
        ):
            key = p.get("imageKey", "")
            scenes[oid_map[p["_id"]]] = {
                "image": oss_signed_url(key) if key else "",
                "topic": p.get("topic", ""),
            }
    for i in items:
        sc = scenes.get(i.get("practiceId"))
        i["sceneImageUrl"] = sc["image"] if sc else ""
        i["topic"] = sc["topic"] if sc else ""
    return items


@router.post("/{rid}/review")
async def review_item(rid: str, req: ReviewRequest, userId: str = Query(...)):
    try:
        item = await get_db().reviewItems.find_one({"_id": ObjectId(rid), "userId": userId})
    except Exception:
        raise HTTPException(404, "复习项不存在")
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
        {"_id": ObjectId(rid)},
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
async def delete_item(rid: str, userId: str = Query(...)):
    try:
        result = await get_db().reviewItems.delete_one({"_id": ObjectId(rid), "userId": userId})
    except Exception:
        raise HTTPException(404, "复习项不存在")
    if result.deleted_count == 0:
        raise HTTPException(404, "复习项不存在")
    return {"ok": True}
