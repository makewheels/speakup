from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from services.oss_storage import get_url as oss_signed_url
from services.translator import translate_to_chinese
from utils.data_source import normalize_source_type
from utils.id_generator import review_item_id
from utils.mongo_ids import id_filter, id_values

router = APIRouter(prefix="/api/review-items", tags=["review-items"])


class AddItemsRequest(BaseModel):
    userId: str
    items: list[dict]


class ReviewRequest(BaseModel):
    remembered: bool


# 错题本拆分两类：mistake=说错的点（corrector gap 自动收录），note=好表达笔记（用户主动记）
_KINDS = {"mistake", "note"}


def normalize_kind(kind) -> str:
    return kind if kind in _KINDS else "mistake"


def review_kind_filter(kind) -> dict:
    """按归一化 kind 查重；历史缺失/非法 kind 与列表读取一致，均视为 mistake。"""
    normalized = normalize_kind(kind)
    if normalized == "note":
        return {"kind": "note"}
    return {"kind": {"$ne": "note"}}


async def reactivate_review_item(rid: str, now: datetime) -> None:
    """已收纳的表达又说错 → 回到错题本：重置调度字段，立即待复习。"""
    await get_db().reviewItems.update_one(
        id_filter(rid),
        {
            "$set": {
                "status": "active",
                "nextReviewAt": now,
                "reviewCount": 0,
                "interval": 1,
                "easiness": 2.5,
            },
            "$unset": {"retiredAt": "", "retiredBy": ""},
        },
    )


@router.post("")
async def add_items(req: AddItemsRequest, token_user_id: str = Depends(current_user_id)):
    assert_same_user(req.userId, token_user_id)
    user = await get_db().users.find_one(id_filter(token_user_id), {"sourceType": 1})
    source_type = normalize_source_type((user or {}).get("sourceType"))
    now = datetime.now(timezone.utc)
    added = 0
    ids = []  # 与 req.items 顺序对应：每条返回新建或已存在的 reviewItem id，方便前端「取消收录」
    for it in req.items:
        kind = normalize_kind(it.get("kind"))
        existing = await get_db().reviewItems.find_one(
            {
                "userId": req.userId,
                "expression": it["expression"],
                **review_kind_filter(kind),
            }
        )
        if existing:
            ids.append(str(existing["_id"]))
            if existing.get("status") == "retired":
                await reactivate_review_item(str(existing["_id"]), now)
            continue
        rid = review_item_id()
        await get_db().reviewItems.insert_one({
            "_id": rid,
            "userId": req.userId,
            "sourceType": source_type,
            "kind": kind,
            "expression": it["expression"],
            "original": it.get("original", ""),
            "note": it.get("note", ""),
            "chinese": it.get("chinese", ""),
            "contextSentence": it.get("contextSentence", ""),
            "practiceId": it.get("practiceId", ""),
            "attemptId": it.get("attemptId", ""),
            "attemptIndex": it.get("attemptIndex", -1),
            "status": "active",
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
    includeRetired: bool = False,
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    filter = {"userId": userId}
    if not includeRetired:
        filter["status"] = {"$ne": "retired"}
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
        i["kind"] = normalize_kind(i.get("kind"))  # 历史数据无 kind 按错题兼容
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
    now = datetime.now(timezone.utc)
    if req.remembered:
        # 错题本语义：会说即收纳，复习队列不再出现（列表里已收纳区可查看/恢复）
        item["status"] = "retired"
        item["retiredAt"] = now
        item["retiredBy"] = "self"
        await get_db().reviewItems.update_one(
            id_filter(rid),
            {"$set": {
                "reviewCount": item["reviewCount"],
                "status": "retired",
                "retiredAt": item["retiredAt"],
                "retiredBy": "self",
            }},
        )
    else:
        item["easiness"] = max(1.3, item["easiness"] - 0.3)
        item["interval"] = 1
        item["nextReviewAt"] = now + timedelta(days=item["interval"])
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


@router.post("/{rid}/restore")
async def restore_item(
    rid: str,
    userId: str = Query(...),
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    item = await get_db().reviewItems.find_one({**id_filter(rid), "userId": token_user_id})
    if not item:
        raise HTTPException(404, "复习项不存在")
    now = datetime.now(timezone.utc)
    await get_db().reviewItems.update_one(
        id_filter(rid),
        {
            "$set": {"status": "active", "nextReviewAt": now},
            "$unset": {"retiredAt": "", "retiredBy": ""},
        },
    )
    item["status"] = "active"
    item["nextReviewAt"] = now
    item.pop("retiredAt", None)
    item.pop("retiredBy", None)
    item["_id"] = str(item["_id"])
    return item


@router.post("/{rid}/translate")
async def translate_item(
    rid: str,
    userId: str = Query(...),
    token_user_id: str = Depends(current_user_id),
):
    """缺 chinese 的复习项（历史数据）首次复习时惰性翻译并落库。"""
    assert_same_user(userId, token_user_id)
    item = await get_db().reviewItems.find_one({**id_filter(rid), "userId": token_user_id})
    if not item:
        raise HTTPException(404, "复习项不存在")
    chinese = (item.get("chinese") or "").strip()
    if not chinese:
        chinese = await translate_to_chinese(
            item.get("expression", ""),
            link_to={"reviewItemId": rid, "userId": token_user_id},
        )
        if chinese:
            await get_db().reviewItems.update_one(
                id_filter(rid), {"$set": {"chinese": chinese}}
            )
    return {"chinese": chinese}


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
