"""阿里云 OSS 对象存储服务。私有桶：只存 key，URL 一律读取时现签。"""

import asyncio

import oss2

from config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET

_bucket = None


def _get_bucket() -> oss2.Bucket:
    global _bucket
    if _bucket is None:
        auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
        _bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)
    return _bucket


def upload_bytes(key: str, data: bytes, content_type: str = "image/jpeg") -> None:
    """同步上传字节数据到 OSS。"""
    _get_bucket().put_object(key, data, headers={"Content-Type": content_type})


async def upload_bytes_async(key: str, data: bytes, content_type: str = "image/jpeg") -> None:
    """异步上传字节数据（在线程池运行同步 SDK）。"""
    await asyncio.to_thread(upload_bytes, key, data, content_type)


def download_bytes(key: str) -> bytes:
    """读取私有对象字节，不生成可外泄的长效地址。"""
    return _get_bucket().get_object(key).read()


async def download_bytes_async(key: str) -> bytes:
    return await asyncio.to_thread(download_bytes, key)


def get_url(key: str) -> str:
    """生成签名 URL（1 小时有效），私有桶浏览器可临时访问。"""
    return _get_bucket().sign_url("GET", key, 3600)


def delete(key: str) -> None:
    _get_bucket().delete_object(key)


async def delete_async(key: str) -> None:
    """异步删除对象（在线程池运行同步 SDK）。"""
    await asyncio.to_thread(delete, key)


def exists(key: str) -> bool:
    return _get_bucket().object_exists(key)
