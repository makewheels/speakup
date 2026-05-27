"""file_service 单元测试：mock httpx + OSS + DB，不依赖真实外部服务。"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

FAKE_IMAGE = b"\xff\xd8\xff" + b"\x00" * 100
FAKE_MD5 = hashlib.md5(FAKE_IMAGE).hexdigest()
FAKE_OSS_URL = "https://bucket.oss-cn-beijing.aliyuncs.com/files/f_test/orig.jpg"


def _http_ctx(content: bytes, content_type: str = "image/jpeg"):
    """构造 mock httpx.AsyncClient context manager。"""
    response = MagicMock()
    response.content = content
    response.headers = {"content-type": content_type}
    response.raise_for_status = MagicMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=response)))
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_db(existing_doc=None):
    """构造 mock DB，files 集合支持 find_one / insert_one。"""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=existing_doc)
    col.insert_one = AsyncMock()
    db = MagicMock()
    db.files = col
    return db


@patch("services.file_service.upload_bytes_async", new_callable=AsyncMock)
@patch("services.file_service.httpx.AsyncClient")
@patch("services.file_service.get_db")
async def test_new_image_uploaded(mock_get_db, mock_http_cls, mock_upload):
    mock_get_db.return_value = _mock_db(existing_doc=None)
    mock_http_cls.return_value = _http_ctx(FAKE_IMAGE)
    mock_upload.return_value = FAKE_OSS_URL

    from services.file_service import get_or_upload_from_url
    doc = await get_or_upload_from_url("https://example.com/img.jpg", topic="city")

    assert doc["md5"] == FAKE_MD5
    assert doc["_id"].startswith("f_")
    assert doc["variants"]["orig"]["url"] == FAKE_OSS_URL
    assert doc["topic"] == "city"
    mock_upload.assert_called_once()
    mock_get_db.return_value.files.insert_one.assert_called_once()


@patch("services.file_service.upload_bytes_async", new_callable=AsyncMock)
@patch("services.file_service.httpx.AsyncClient")
@patch("services.file_service.get_db")
async def test_dedup_skips_upload(mock_get_db, mock_http_cls, mock_upload):
    """MD5 已存在时，不重复上传到 OSS，不插入新记录。"""
    existing = {
        "_id": "f_existing123",
        "md5": FAKE_MD5,
        "variants": {"orig": {"url": FAKE_OSS_URL, "key": "files/f_existing123/orig.jpg", "bytes": 103}},
        "status": "active",
    }
    mock_get_db.return_value = _mock_db(existing_doc=existing)
    mock_http_cls.return_value = _http_ctx(FAKE_IMAGE)
    mock_upload.return_value = FAKE_OSS_URL

    from services.file_service import get_or_upload_from_url
    doc = await get_or_upload_from_url("https://example.com/img.jpg")

    assert doc["_id"] == "f_existing123"
    mock_upload.assert_not_called()
    mock_get_db.return_value.files.insert_one.assert_not_called()


@patch("services.file_service.upload_bytes_async", new_callable=AsyncMock)
@patch("services.file_service.httpx.AsyncClient")
@patch("services.file_service.get_db")
async def test_oss_key_uses_file_id(mock_get_db, mock_http_cls, mock_upload):
    """上传的 OSS key 格式为 files/{fileId}/orig.{ext}。"""
    mock_get_db.return_value = _mock_db(existing_doc=None)
    mock_http_cls.return_value = _http_ctx(FAKE_IMAGE)
    mock_upload.return_value = FAKE_OSS_URL

    from services.file_service import get_or_upload_from_url
    doc = await get_or_upload_from_url("https://example.com/img.jpg")

    key_arg = mock_upload.call_args[0][0]
    fid = doc["_id"]
    assert key_arg == f"files/{fid}/orig.jpg"


@patch("services.file_service.upload_bytes_async", new_callable=AsyncMock)
@patch("services.file_service.httpx.AsyncClient")
@patch("services.file_service.get_db")
async def test_png_mime_uses_png_ext(mock_get_db, mock_http_cls, mock_upload):
    mock_get_db.return_value = _mock_db(existing_doc=None)
    mock_http_cls.return_value = _http_ctx(FAKE_IMAGE, content_type="image/png")
    mock_upload.return_value = FAKE_OSS_URL

    from services.file_service import get_or_upload_from_url
    doc = await get_or_upload_from_url("https://example.com/img.png")

    key_arg = mock_upload.call_args[0][0]
    assert key_arg.endswith("orig.png")
