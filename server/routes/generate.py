from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.image_generator import get_next_image, start_prefetch

router = APIRouter(prefix="/api/generate", tags=["generate"])


class UserRequest(BaseModel):
    userId: str


@router.post("/next")
async def next_image(req: UserRequest):
    try:
        return await get_next_image(req.userId)
    except Exception as e:
        raise HTTPException(500, "图片生成失败")


@router.post("/prefetch")
async def prefetch(req: UserRequest):
    import asyncio
    asyncio.create_task(start_prefetch(req.userId))
    return {"ok": True}
