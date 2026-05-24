from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId
from db.connection import get_db

router = APIRouter(prefix="/api/vocabulary", tags=["vocabulary"])


class AddWordsRequest(BaseModel):
    userId: str
    words: list[dict]


class ReviewRequest(BaseModel):
    remembered: bool


@router.post("")
async def add_words(req: AddWordsRequest):
    added = 0
    for w in req.words:
        existing = await get_db().vocabulary.find_one({"userId": req.userId, "word": w["word"]})
        if existing:
            continue
        await get_db().vocabulary.insert_one({
            "userId": req.userId,
            "word": w["word"],
            "chinese": w.get("chinese", ""),
            "contextSentence": w.get("contextSentence", ""),
            "sessionId": w.get("sessionId", ""),
            "nextReviewAt": datetime.utcnow(),
            "reviewCount": 0,
            "interval": 1,
            "easiness": 2.5,
        })
        added += 1
    return {"added": added}


@router.get("/")
async def list_vocabulary(userId: str = Query(...), due: bool = False):
    filter = {"userId": userId}
    if due:
        filter["nextReviewAt"] = {"$lte": datetime.utcnow()}
    cursor = get_db().vocabulary.find(filter).sort("nextReviewAt", 1)
    items = []
    async for item in cursor:
        item["_id"] = str(item["_id"])
        items.append(item)
    return items


@router.post("/{vid}/review")
async def review_word(vid: str, req: ReviewRequest):
    try:
        item = await get_db().vocabulary.find_one({"_id": ObjectId(vid)})
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

    item["nextReviewAt"] = datetime.utcnow() + timedelta(days=item["interval"])
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
async def delete_word(vid: str):
    await get_db().vocabulary.delete_one({"_id": ObjectId(vid)})
    return {"ok": True}
