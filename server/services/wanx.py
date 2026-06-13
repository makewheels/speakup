"""通义万相文生图（DashScope multimodal-generation 同步接口）。"""

import httpx

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, IMAGE_MODEL

WANX_MODEL = IMAGE_MODEL
GEN_URL = f"{DASHSCOPE_BASE_URL}/api/v1/services/aigc/multimodal-generation/generation"

PHOTO_STYLE = (
    "realistic photograph, natural lighting, shot on 35mm, candid documentary style, "
    "first-person customer point of view, no text, no watermark"
)


async def wanx_generate(prompt: str, size: str = "1280*720") -> bytes:
    """同步生图（约 10~30 秒），返回图片字节。"""
    async with httpx.AsyncClient(timeout=120.0) as c:
        resp = await c.post(
            GEN_URL,
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            json={
                "model": WANX_MODEL,
                "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                "parameters": {"size": size, "n": 1},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "output" not in data:
            raise RuntimeError(f"万相生图失败: {data}")
        content = data["output"]["choices"][0]["message"]["content"]
        image_url = next(item["image"] for item in content if "image" in item)
        img = await c.get(image_url)
        img.raise_for_status()
        return img.content
