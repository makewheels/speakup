"""场景配图 key 与生成。"""

from config import IMAGE_ENABLED
from services import oss_storage, wanx


def scenario_image_key(sid: str) -> str:
    return f"scenarios/{sid}/cover.jpg"


async def maybe_gen_image(
    sid: str,
    image_prompt: str,
    link: dict | None = None,
    generator=None,
) -> str:
    """生成配图存 OSS，返回 imageKey。IMAGE_ENABLED=false 时跳过生成、返回空串（前端按无图渲染）。"""
    if not IMAGE_ENABLED or not image_prompt:
        return ""
    generate = generator or wanx.wanx_generate
    image = await generate(f"{image_prompt}, {wanx.PHOTO_STYLE}", link_to=link)
    key = scenario_image_key(sid)
    await oss_storage.upload_bytes_async(key, image, "image/jpeg")
    return key
