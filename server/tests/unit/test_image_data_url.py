"""Tests for the image → data-URL helper that bypasses DashScope's slow refetch."""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

from services.corrector import _to_data_url


def _fake_httpx_client(content: bytes, content_type: str = "image/jpeg", status: int = 200):
    """Mock httpx.AsyncClient as a context manager returning a response."""
    resp = MagicMock()
    resp.content = content
    resp.headers = {"content-type": content_type}
    if status >= 400:
        resp.raise_for_status = MagicMock(side_effect=Exception(f"HTTP {status}"))
    else:
        resp.raise_for_status = MagicMock()

    inner = MagicMock()
    inner.get = AsyncMock(return_value=resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=inner)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


def test_http_url_is_inlined_as_base64_data_url():
    content = b"\x89PNG\r\n-fake-png-bytes-"
    with patch("services.corrector.httpx.AsyncClient", _fake_httpx_client(content, "image/png")):
        result = asyncio.run(_to_data_url("https://example.com/img.png"))
    assert result.startswith("data:image/png;base64,")
    _, payload = result.split(",", 1)
    assert base64.b64decode(payload) == content


def test_https_url_is_inlined():
    with patch("services.corrector.httpx.AsyncClient", _fake_httpx_client(b"jpg-bytes")):
        result = asyncio.run(_to_data_url("https://cdn.example.com/x.jpg"))
    assert result.startswith("data:image/jpeg;base64,")


def test_existing_data_url_passes_through_untouched():
    src = "data:image/png;base64,AAAA"
    # AsyncClient should never be called
    fake = MagicMock(side_effect=AssertionError("should not fetch a data URL"))
    with patch("services.corrector.httpx.AsyncClient", fake):
        result = asyncio.run(_to_data_url(src))
    assert result == src


def test_empty_url_passes_through():
    assert asyncio.run(_to_data_url("")) == ""


def test_non_http_url_passes_through():
    src = "file:///tmp/x.jpg"
    result = asyncio.run(_to_data_url(src))
    assert result == src


def test_fetch_failure_falls_back_to_original_url():
    """We never want the AI call to fail just because the image host is down."""
    src = "https://broken.example.com/x.jpg"

    def raising_client(*a, **kw):
        raise OSError("network down")

    with patch("services.corrector.httpx.AsyncClient", raising_client):
        result = asyncio.run(_to_data_url(src))
    assert result == src


def test_non_image_content_type_defaults_to_jpeg():
    with patch(
        "services.corrector.httpx.AsyncClient",
        _fake_httpx_client(b"x", content_type="application/octet-stream"),
    ):
        result = asyncio.run(_to_data_url("https://example.com/blob"))
    assert result.startswith("data:image/jpeg;base64,")


def test_correct_text_inlines_image_before_sending_to_llm():
    """End-to-end-ish: correct_text should pass a data URL (not the original) to the LLM."""
    import json

    from services.corrector import correct_text

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "summary": "ok", "nativeVersion": "x", "gaps": [],
    })))]
    fake_llm = MagicMock()
    fake_llm.chat.completions.create = AsyncMock(return_value=fake_resp)

    fetched = b"FAKE-JPEG-BYTES"
    with patch("services.corrector.httpx.AsyncClient", _fake_httpx_client(fetched)), \
         patch("services.corrector._get_client", return_value=fake_llm):
        asyncio.run(correct_text("A cat on the table.", "https://loremflickr.com/640/640/cat"))

    messages = fake_llm.chat.completions.create.await_args.kwargs["messages"]
    image_block = next(b for b in messages[-1]["content"] if b.get("type") == "image_url")
    assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")
