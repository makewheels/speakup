from fastapi import APIRouter, HTTPException
from services.image_generator import get_next_image

router = APIRouter(prefix="/api/generate", tags=["generate"])


@router.post("/next")
async def next_image():
    try:
        return await get_next_image()
    except Exception:
        raise HTTPException(500, "图片生成失败")
