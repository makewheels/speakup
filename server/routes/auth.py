import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.connection import get_db
from services.auth_tokens import create_session
from utils.id_generator import user_id

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
        uid = user_id()
        await get_db().users.insert_one({
            "_id": uid,
            "phone": req.phone,
            "nickname": nickname,
            "createdAt": now,
            "lastLoginAt": now,
        })
        user = {"_id": uid, "phone": req.phone, "nickname": nickname}
    else:
        await get_db().users.update_one({"_id": user["_id"]}, {"$set": {"lastLoginAt": now}})

    uid = str(user["_id"])
    token = await create_session(uid)
    return {"userId": uid, "phone": req.phone, "nickname": user["nickname"], "token": token}
