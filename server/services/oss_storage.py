"""阿里云 OSS 对象存储服务"""

import asyncio

import httpx
import oss2

from config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET

_bucket = None


def _get_bucket() -> oss2.Bucket:
    global _bucket
    if _bucket is None:
        auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
        _bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)
    return _bucket


def image_key(user_id: str, session_id: str) -> str:
    """OSS 对象 key：images/{userId}/{sessionId}.jpg
    bucket 本身已区分 dev/prod，key 里不重复存环境信息。
    """
    return f"images/{user_id}/{session_id}.jpg"


def _public_url(key: str) -> str:
    return f"{OSS_ENDPOINT.replace('https://', f'https://{OSS_BUCKET}.')}/{key}"


def upload_bytes(key: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """同步上传字节数据到 OSS，返回公网 URL。"""
    _get_bucket().put_object(key, data, headers={"Content-Type": content_type})
    return _public_url(key)


async def upload_bytes_async(key: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """异步上传字节数据（在线程池运行同步 SDK）。"""
    return await asyncio.to_thread(upload_bytes, key, data, content_type)


async def upload_from_url(key: str, url: str, timeout: float = 20.0) -> str:
    """从 URL 下载图片并上传到 OSS，返回公网 URL。"""
    if not OSS_ACCESS_KEY_ID or not OSS_ACCESS_KEY_SECRET:
        raise ValueError("OSS credentials not configured")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        resp = await c.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"
        return await upload_bytes_async(key, resp.content, content_type)


def upload_file(key: str, filepath: str) -> str:
    """上传本地文件到 OSS，返回公网 URL。"""
    _get_bucket().put_object_from_file(key, filepath)
    return _public_url(key)


def get_url(key: str) -> str:
    """生成签名 URL（1 小时有效）。"""
    return _get_bucket().sign_url("GET", key, 3600)


def delete(key: str) -> None:
    _get_bucket().delete_object(key)


def exists(key: str) -> bool:
    return _get_bucket().object_exists(key)
