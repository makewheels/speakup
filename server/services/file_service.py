"""文件管理服务：files 集合 + OSS 存储，MD5 去重，支持图片/视频。

OSS 路径：files/{fileId}/orig.jpg
DB 集合：files
"""

import hashlib
from datetime import datetime, timezone

import httpx

from db.connection import get_db
from services.oss_storage import upload_bytes_async, _public_url
from utils.id_generator import file_id


def _oss_key(fid: str, variant: str, ext: str = "jpg") -> str:
    return f"files/{fid}/{variant}.{ext}"


def _ext_from_mime(mime: str) -> str:
    return {"image/jpeg": "jpg", "image/png": "png",
            "image/webp": "webp", "video/mp4": "mp4"}.get(mime, "bin")


async def get_or_upload_from_url(
    url: str,
    source: str = "loremflickr",
    topic: str = "",
    timeout: float = 20.0,
) -> dict:
    """从 URL 下载文件，MD5 去重后上传到 OSS，返回 files 文档。
    若已存在相同 MD5，直接返回已有记录，不重复上传。
    """
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        resp = await c.get(url)
        resp.raise_for_status()
        data = resp.content
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not mime.startswith(("image/", "video/")):
            mime = "image/jpeg"

    md5 = hashlib.md5(data).hexdigest()

    existing = await get_db().files.find_one({"md5": md5})
    if existing:
        existing["_id"] = str(existing["_id"])
        return existing

    fid = file_id()
    ext = _ext_from_mime(mime)
    key = _oss_key(fid, "orig", ext)
    oss_url = await upload_bytes_async(key, data, mime)

    doc = {
        "_id": fid,
        "md5": md5,
        "mimeType": mime,
        "source": source,
        "sourceUrl": url,
        "topic": topic,
        "variants": {
            "orig": {"key": key, "url": oss_url, "bytes": len(data)},
        },
        "status": "active",
        "createdAt": datetime.now(timezone.utc),
    }
    await get_db().files.insert_one(doc)
    return doc


async def get_file(fid: str) -> dict | None:
    doc = await get_db().files.find_one({"_id": fid})
    return doc


def orig_url(file_doc: dict) -> str:
    return file_doc["variants"]["orig"]["url"]
