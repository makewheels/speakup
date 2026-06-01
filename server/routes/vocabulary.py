from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId
from db.connection import get_db
from services.oss_storage import sign_public_url

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])


class AddWordsRequest(BaseModel):
    userId: str
    words: list[dict]


class ReviewRequest(BaseModel):
    remembered: bool


@router.post("")
async def add_words(req: AddWordsRequest):
    now = datetime.now(timezone.utc)
    added = 0
    for w in req.words:
        existing = await get_db().vocabulary.find_one({"userId": req.userId, "word": w["word"]})
        if existing:
            continue
        await get_db().vocabulary.insert_one({
            "userId": req.userId,
            "word": w["word"],
            "original": w.get("original", ""),
            "note": w.get("note", ""),
            "contextSentence": w.get("contextSentence", ""),
            "sessionId": w.get("sessionId", ""),
            "createdAt": now,
            "nextReviewAt": now,
            "reviewCount": 0,
            "interval": 1,
            "easiness": 2.5,
        })
        added += 1
    return {"added": added}


@router.get("")
async def list_vocabulary(userId: str = Query(...), due: bool = False):
    filter = {"userId": userId}
    if due:
        filter["nextReviewAt"] = {"$lte": datetime.now(timezone.utc)}
    cursor = get_db().vocabulary.find(filter).sort("nextReviewAt", 1)
    items = []
    async for item in cursor:
        item["_id"] = str(item["_id"])
        items.append(item)

    # 关联 session 补场景图（签名 OSS 优先，loremflickr 兜底）+ topic，供复习卡展示与原图重练
    oid_map = {}
    for sid in {i.get("sessionId") for i in items if i.get("sessionId")}:
        try:
            oid_map[ObjectId(sid)] = sid
        except Exception:
            pass
    scenes = {}
    if oid_map:
        async for s in get_db().sessions.find(
            {"_id": {"$in": list(oid_map)}},
            {"ossImageUrl": 1, "imageUrl": 1, "topic": 1},
        ):
            loremflickr = s.get("imageUrl", "")
            oss = s.get("ossImageUrl")
            scenes[oid_map[s["_id"]]] = {
                "image": sign_public_url(oss) if oss else loremflickr,
                "fallback": loremflickr,
                "topic": s.get("topic", ""),
            }
    for i in items:
        sc = scenes.get(i.get("sessionId"))
        own = i.get("imageUrl", "")
        i["sceneImageUrl"] = (sc["image"] if sc else "") or own
        i["sceneFallbackUrl"] = (sc["fallback"] if sc else "") or own
        i["topic"] = sc["topic"] if sc else ""
    return items


@router.post("/{vid}/review")
async def review_word(vid: str, req: ReviewRequest, userId: str = Query(...)):
    try:
        item = await get_db().vocabulary.find_one({"_id": ObjectId(vid), "userId": userId})
    except Exception:
        raise HTTPException(404, "生词不存在")
    if not item:
        raise HTTPException(404, "生词不存在")

    item["reviewCount"] += 1
    if req.remembered:
        item["easiness"] = min(3.0, item["easiness"] + 0.1)
        item["interval"] = round(item["interval"] * item["easiness"])
    else:
        item["easiness"] = max(1.3, item["easiness"] - 0.3)
        item["interval"] = 1

    item["nextReviewAt"] = datetime.now(timezone.utc) + timedelta(days=item["interval"])
    await get_db().vocabulary.update_one(
        {"_id": ObjectId(vid)},
        {"$set": {
            "reviewCount": item["reviewCount"],
            "easiness": item["easiness"],
            "interval": item["interval"],
            "nextReviewAt": item["nextReviewAt"],
        }},
    )
    item["_id"] = str(item["_id"])
    return item


@router.delete("/{vid}")
async def delete_word(vid: str, userId: str = Query(...)):
    try:
        result = await get_db().vocabulary.delete_one({"_id": ObjectId(vid), "userId": userId})
    except Exception:
        raise HTTPException(404, "生词不存在")
    if result.deleted_count == 0:
        raise HTTPException(404, "生词不存在")
    return {"ok": True}
