import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.connection import get_db
from services.image_generator import start_prefetch

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    phone: str


@router.post("/login")
async def login(req: LoginRequest):
    if not re.match(r"^1\d{10}$", req.phone):
        raise HTTPException(400, "请输入正确的手机号")

    user = await get_db().users.find_one({"phone": req.phone})
    if not user:
        result = await get_db().users.insert_one({
            "phone": req.phone,
            "nickname": f"用户{req.phone[-4:]}",
            "lastLoginAt": None,
        })
        user = {"_id": result.inserted_id, "phone": req.phone, "nickname": f"用户{req.phone[-4:]}"}

    await get_db().users.update_one({"_id": user["_id"]}, {"$set": {"lastLoginAt": None}})

    user_id = str(user["_id"])
    import asyncio as _asyncio
    _asyncio.create_task(start_prefetch(user_id))

    return {"userId": user_id, "phone": req.phone, "nickname": user["nickname"]}
