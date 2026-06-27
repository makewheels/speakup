import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Header, HTTPException

from db.connection import get_db


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await get_db().authSessions.insert_one({
        "_id": _digest(token),
        "userId": user_id,
        "createdAt": now,
        "lastUsedAt": now,
    })
    return token


async def current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(401, "请先登录")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "登录状态无效，请重新登录")

    token_hash = _digest(token.strip())
    session = await get_db().authSessions.find_one({"_id": token_hash})
    if not session:
        raise HTTPException(401, "登录状态已失效，请重新登录")

    await get_db().authSessions.update_one(
        {"_id": token_hash},
        {"$set": {"lastUsedAt": datetime.now(timezone.utc)}},
    )
    return session["userId"]


def assert_same_user(request_user_id: str, token_user_id: str) -> None:
    if request_user_id != token_user_id:
        raise HTTPException(403, "不能操作其他用户的数据")
