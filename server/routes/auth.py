import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.connection import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    phone: str


@router.post("/login")
async def login(req: LoginRequest):
    if not re.match(r"^1\d{10}$", req.phone):
        raise HTTPException(400, "请输入正确的手机号")

    now = datetime.now(timezone.utc)
    user = await get_db().users.find_one({"phone": req.phone})
    if not user:
        nickname = f"User{req.phone[-4:]}"
        result = await get_db().users.insert_one({
            "phone": req.phone,
            "nickname": nickname,
            "createdAt": now,
            "lastLoginAt": now,
        })
        user = {"_id": result.inserted_id, "phone": req.phone, "nickname": nickname}
    else:
        await get_db().users.update_one({"_id": user["_id"]}, {"$set": {"lastLoginAt": now}})

    return {"userId": str(user["_id"]), "phone": req.phone, "nickname": user["nickname"]}
