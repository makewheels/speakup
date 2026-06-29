"""场景视频 key 与生成。"""

import logging

from config import VIDEO_ENABLED
from services import oss_storage, volc_video

logger = logging.getLogger(__name__)

VIDEO_STYLE = (
    "5-second silent realistic documentary video, natural motion, wide shot, "
    "first-person customer point of view, no subtitles, no text, no watermark"
)


def scenario_video_key(sid: str) -> str:
    return f"scenarios/{sid}/cover.mp4"


async def maybe_gen_video(
    sid: str,
    video_prompt: str,
    link: dict | None = None,
    generator=None,
) -> str:
    """生成场景视频存 OSS，失败返回空串，让图片/无图兜底。"""
    if not VIDEO_ENABLED or not video_prompt:
        return ""
    generate = generator or volc_video.video_generate
    try:
        video = await generate(f"{video_prompt}, {VIDEO_STYLE}", link_to=link)
        key = scenario_video_key(sid)
        await oss_storage.upload_bytes_async(key, video, "video/mp4")
        return key
    except Exception as exc:
        logger.warning("scenario video generation failed for %s: %s", sid, exc)
        return ""
