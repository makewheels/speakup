"""阿里云 OSS 对象存储服务。私有桶：只存 key，URL 一律读取时现签。"""

import asyncio
from dataclasses import dataclass
from collections.abc import Iterator

import oss2

from config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET

_bucket = None


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str
    crc64: int | None
    last_modified: int | None = None


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


def object_info(key: str) -> ObjectInfo:
    result = _get_bucket().head_object(key)
    return ObjectInfo(
        key=key,
        size=int(result.content_length or 0),
        etag=result.etag or "",
        crc64=getattr(result, "server_crc", None),
        last_modified=getattr(result, "last_modified", None),
    )


def iter_objects(prefix: str) -> Iterator[ObjectInfo]:
    for item in oss2.ObjectIteratorV2(_get_bucket(), prefix=prefix):
        yield ObjectInfo(
            key=item.key,
            size=int(item.size or 0),
            etag=item.etag or "",
            crc64=None,
            last_modified=getattr(item, "last_modified", None),
        )


def copy_verified(source_key: str, target_key: str) -> ObjectInfo:
    """同桶复制并按大小、ETag 和可用时的 CRC64 校验；可重复执行。"""
    source = object_info(source_key)
    if not exists(target_key):
        _get_bucket().copy_object(OSS_BUCKET, source_key, target_key)
    target = object_info(target_key)
    if source.size != target.size or (source.etag and source.etag != target.etag):
        raise RuntimeError(f"OSS copy verification failed: {source_key} -> {target_key}")
    if source.crc64 is not None and target.crc64 is not None and source.crc64 != target.crc64:
        raise RuntimeError(f"OSS CRC verification failed: {source_key} -> {target_key}")
    return target
