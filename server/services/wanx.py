"""通义万相文生图。

老 endpoint `/aigc/multimodal-generation/generation`（同步）只接受 wanx-v1 / wan2.7-image
等"老"模型；新一代便宜款 wanx2.1-t2i-turbo / wan2.2-t2i-flash 走 `/aigc/text2image/image-synthesis`
异步 API，要 POST 拿 task_id 然后轮询。两条路这里都支持，按 IMAGE_MODEL 自动选。
"""

import asyncio

import httpx

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, IMAGE_MODEL
from services.llm_audit import log_image_call

WANX_MODEL = IMAGE_MODEL

# 同步 endpoint：wanx-v1 / wan2.7-image 等老模型
SYNC_URL = f"{DASHSCOPE_BASE_URL}/api/v1/services/aigc/multimodal-generation/generation"
# 异步 endpoint：wanx2.x 系列（turbo / flash / plus）
ASYNC_CREATE_URL = f"{DASHSCOPE_BASE_URL}/api/v1/services/aigc/text2image/image-synthesis"
ASYNC_TASK_URL = f"{DASHSCOPE_BASE_URL}/api/v1/tasks"

# 走异步 API 的模型前缀（更便宜的新一代）
_ASYNC_PREFIXES = ("wanx2.", "wan2.2-", "wanx-2.")


def _is_async_model(model: str) -> bool:
    return any(model.startswith(p) for p in _ASYNC_PREFIXES)


PHOTO_STYLE = (
    "realistic photograph, natural lighting, shot on 35mm, candid documentary style, "
    "first-person customer point of view, no text, no watermark"
)


async def _generate_sync(prompt: str, size: str) -> bytes:
    """老模型同步 endpoint：POST 一次直接拿到图 URL。"""
    async with httpx.AsyncClient(timeout=120.0) as c:
        resp = await c.post(
            SYNC_URL,
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
            raise RuntimeError(f"万相同步生图失败: {data}")
        content = data["output"]["choices"][0]["message"]["content"]
        image_url = next(item["image"] for item in content if "image" in item)
        img = await c.get(image_url)
        img.raise_for_status()
        return img.content


async def _generate_async(prompt: str, size: str) -> bytes:
    """新模型异步 endpoint：POST 拿 task_id → 轮询直到 SUCCEEDED → 下载图。"""
    async with httpx.AsyncClient(timeout=120.0) as c:
        # 1. 创建任务
        create = await c.post(
            ASYNC_CREATE_URL,
            headers={
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                "X-DashScope-Async": "enable",
            },
            json={
                "model": WANX_MODEL,
                "input": {"prompt": prompt},
                "parameters": {"size": size, "n": 1},
            },
        )
        create.raise_for_status()
        task_id = create.json()["output"]["task_id"]

        # 2. 轮询任务（每 2 秒一次，最多 60 秒）
        for _ in range(30):
            await asyncio.sleep(2)
            r = await c.get(
                f"{ASYNC_TASK_URL}/{task_id}",
                headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
            )
            r.raise_for_status()
            data = r.json()
            status = data["output"]["task_status"]
            if status == "SUCCEEDED":
                results = data["output"]["results"]
                if not results:
                    raise RuntimeError(f"task {task_id} 没有 results")
                image_url = results[0]["url"]
                img = await c.get(image_url)
                img.raise_for_status()
                return img.content
            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(f"task {task_id} {status}: {data['output'].get('message')}")
            # 还在 PENDING / RUNNING，继续轮询

        raise RuntimeError(f"task {task_id} 60 秒超时")


async def wanx_generate(
    prompt: str,
    size: str = "1024*576",
    link_to: dict | None = None,
) -> bytes:
    """文生图统一入口。同步 / 异步 endpoint 按模型名自动选。link_to 用于审计挂 scenarioId。"""
    err = None
    image_bytes = b""
    try:
        if _is_async_model(WANX_MODEL):
            image_bytes = await _generate_async(prompt, size)
        else:
            image_bytes = await _generate_sync(prompt, size)
    except Exception as e:
        err = str(e)
        raise
    finally:
        await log_image_call(
            model=WANX_MODEL,
            prompt=prompt,
            size_bytes=len(image_bytes),
            link_to=link_to,
            error=err,
        )
    return image_bytes
