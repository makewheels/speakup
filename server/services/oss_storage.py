"""阿里云 OSS 对象存储服务"""

import oss2
from config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET

_auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
_bucket = oss2.Bucket(_auth, OSS_ENDPOINT, OSS_BUCKET)


def upload_bytes(key: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """上传字节数据到 OSS，返回公网 URL。"""
    _bucket.put_object(key, data, headers={"Content-Type": content_type})
    return f"{OSS_ENDPOINT.replace('https://', f'https://{OSS_BUCKET}.')}/{key}"


def upload_file(key: str, filepath: str) -> str:
    """上传本地文件到 OSS，返回公网 URL。"""
    _bucket.put_object_from_file(key, filepath)
    return f"{OSS_ENDPOINT.replace('https://', f'https://{OSS_BUCKET}.')}/{key}"


def get_url(key: str) -> str:
    """生成签名 URL（1小时有效）。"""
    return _bucket.sign_url("GET", key, 3600)


def delete(key: str) -> None:
    """删除对象。"""
    _bucket.delete_object(key)


def exists(key: str) -> bool:
    """检查对象是否存在。"""
    return _bucket.object_exists(key)
