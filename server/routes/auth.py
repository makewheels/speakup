import re
import time
import unicodedata
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from db.connection import get_db
from services import oss_storage
from services.auth_tokens import create_session, current_user_id
from utils.data_source import normalize_source_type
from utils.id_generator import user_id
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_MAX_AVATAR_BYTES = 5 * 1024 * 1024


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


def _avatar_content_type(data: bytes) -> str | None:
    """按文件签名识别允许的头像类型，不信任扩展名或浏览器 MIME。"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _avatar_url(user: dict) -> str | None:
    if not user.get("avatarKey"):
        return None
    version = user.get("avatarVersion", 0)
    return f"/api/auth/avatar/{user['_id']}?v={version}"


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
        "avatarUrl": _avatar_url(user),
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


@router.post("/profile/avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    token_user_id: str = Depends(current_user_id),
):
    user = await get_db().users.find_one(id_filter(token_user_id))
    if not user:
        raise HTTPException(404, "用户不存在")

    data = await avatar.read(_MAX_AVATAR_BYTES + 1)
    if not data:
        raise HTTPException(400, "头像文件不能为空")
    if len(data) > _MAX_AVATAR_BYTES:
        raise HTTPException(413, "头像文件不能超过 5 MB")
    content_type = _avatar_content_type(data)
    if not content_type:
        raise HTTPException(400, "头像仅支持 JPG、PNG 或 WebP")

    key = f"users/{token_user_id}/avatar/current"
    try:
        await oss_storage.upload_bytes_async(key, data, content_type)
    except Exception as exc:
        logger.exception("头像上传到 OSS 失败")
        raise HTTPException(502, "头像上传失败，请稍后重试") from exc

    now = datetime.now(timezone.utc)
    version = int(time.time() * 1000)
    result = await get_db().users.update_one(
        id_filter(token_user_id),
        {"$set": {"avatarKey": key, "avatarVersion": version, "updatedAt": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "用户不存在")
    return {
        "userId": token_user_id,
        "avatarUrl": f"/api/auth/avatar/{token_user_id}?v={version}",
    }


@router.delete("/profile/avatar")
async def remove_avatar(token_user_id: str = Depends(current_user_id)):
    user = await get_db().users.find_one(id_filter(token_user_id))
    if not user:
        raise HTTPException(404, "用户不存在")

    await get_db().users.update_one(
        id_filter(token_user_id),
        {
            "$unset": {"avatarKey": "", "avatarVersion": ""},
            "$set": {"updatedAt": datetime.now(timezone.utc)},
        },
    )
    if user.get("avatarKey"):
        try:
            await oss_storage.delete_async(user["avatarKey"])
        except Exception:
            # 用户资料已恢复默认头像；对象清理由后续同 key 上传覆盖，不阻塞当前操作。
            logger.warning("头像 OSS 对象清理失败: user=%s", token_user_id, exc_info=True)
    return {"userId": token_user_id, "avatarUrl": None}


@router.get("/avatar/{avatar_user_id}")
async def read_avatar(avatar_user_id: str):
    """用稳定版本化地址跳转到私有 OSS 的一小时签名 URL。"""
    user = await get_db().users.find_one(id_filter(avatar_user_id))
    if not user or not user.get("avatarKey"):
        raise HTTPException(404, "头像不存在")
    return RedirectResponse(
        oss_storage.get_url(user["avatarKey"]),
        status_code=307,
        headers={"Cache-Control": "public, max-age=3600"},
    )
