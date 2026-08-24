import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import create_session, current_user_id
from utils.data_source import normalize_source_type
from utils.id_generator import user_id
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    phone: str
    sourceType: Literal["human", "ai_test"] = "human"


class UpdateProfileRequest(BaseModel):
    nickname: str


def _normalize_nickname(value: str) -> str:
    nickname = " ".join(value.split())
    if not 1 <= len(nickname) <= 24:
        raise HTTPException(400, "昵称长度应为 1–24 个字符")
    if any(unicodedata.category(char) == "Cc" for char in nickname):
        raise HTTPException(400, "昵称包含不支持的字符")
    return nickname


@router.post("/login")
async def login(req: LoginRequest):
    if not re.match(r"^1\d{10}$", req.phone):
        raise HTTPException(400, "请输入正确的手机号")

    now = datetime.now(timezone.utc)
    user = await get_db().users.find_one({"phone": req.phone})
    if not user:
        nickname = f"User{req.phone[-4:]}"
        uid = user_id()
        source_type = req.sourceType
        await get_db().users.insert_one({
            "_id": uid,
            "phone": req.phone,
            "nickname": nickname,
            "sourceType": source_type,
            "createdAt": now,
            "lastLoginAt": now,
        })
        user = {
            "_id": uid,
            "phone": req.phone,
            "nickname": nickname,
            "sourceType": source_type,
        }
    else:
        source_type = normalize_source_type(user.get("sourceType"))
        await get_db().users.update_one(
            {"_id": user["_id"]},
            {"$set": {"lastLoginAt": now, "sourceType": source_type}},
        )

    uid = str(user["_id"])
    token = await create_session(uid)
    return {
        "userId": uid,
        "phone": req.phone,
        "nickname": user["nickname"],
        "sourceType": source_type,
        "token": token,
    }


@router.patch("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    token_user_id: str = Depends(current_user_id),
):
    nickname = _normalize_nickname(req.nickname)
    result = await get_db().users.update_one(
        id_filter(token_user_id),
        {"$set": {"nickname": nickname, "updatedAt": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "用户不存在")
    return {"userId": token_user_id, "nickname": nickname}
