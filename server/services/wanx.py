"""场景配图生成。

默认接火山方舟 Agent Plan Seedream 图片接口。文件名沿用 `wanx.py`，
是为了不改业务调用方。
"""

import base64

import httpx

from config import IMAGE_API_KEY, IMAGE_BASE_URL, IMAGE_MODEL, IMAGE_SIZE
from services.llm_audit import log_image_call

IMAGE_URL = f"{IMAGE_BASE_URL}/images/generations"

PHOTO_STYLE = (
    "realistic photograph, natural lighting, shot on 35mm, candid documentary style, "
    "first-person customer point of view, no text, no watermark"
)


def _volc_size(size: str | None) -> str:
    """历史配置使用 1024*576；方舟图片接口使用 2560x1440 这类写法。"""
    return (size or IMAGE_SIZE).replace("*", "x")


async def _download_or_decode_image(c: httpx.AsyncClient, item: dict) -> bytes:
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    image_url = item.get("url") or item.get("image_url")
    if not image_url:
        raise RuntimeError(f"火山方舟生图失败: {item}")
    img = await c.get(image_url)
    img.raise_for_status()
    return img.content


async def wanx_generate(
    prompt: str,
    size: str | None = None,
    link_to: dict | None = None,
) -> bytes:
    """文生图统一入口。link_to 用于审计挂 scenarioId。"""
    err = None
    image_bytes = b""
    request_size = _volc_size(size)
    try:
        async with httpx.AsyncClient(timeout=180.0) as c:
            resp = await c.post(
                IMAGE_URL,
                headers={
                    "Authorization": f"Bearer {IMAGE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": IMAGE_MODEL,
                    "prompt": prompt,
                    "size": request_size,
                    "n": 1,
                    "response_format": "url",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            if not items:
                raise RuntimeError(f"火山方舟生图失败: {data}")
            image_bytes = await _download_or_decode_image(c, items[0])
            return image_bytes
    except Exception as e:
        err = str(e)
        raise
    finally:
        await log_image_call(
            model=IMAGE_MODEL,
            prompt=prompt,
            size_bytes=len(image_bytes),
            link_to=link_to,
            error=err,
        )
