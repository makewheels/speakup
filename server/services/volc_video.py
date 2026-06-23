"""火山方舟 Agent Plan 视频生成 API 轻封装。

当前 SpeakUp 产品路径没有视频生成入口；这里先提供 service，供脚本或后续路由复用。
"""

from typing import Any

import httpx

from config import VIDEO_API_KEY, VIDEO_BASE_URL, VIDEO_MODEL

TASKS_URL = f"{VIDEO_BASE_URL}/contents/generations/tasks"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {VIDEO_API_KEY}",
        "Content-Type": "application/json",
    }


async def create_video_task(
    prompt: str,
    *,
    model: str | None = None,
    content: list[dict[str, Any]] | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "model": model or VIDEO_MODEL,
        "content": content or [{"type": "text", "text": prompt}],
    }
    if parameters:
        payload.update(parameters)

    async with httpx.AsyncClient(timeout=60.0) as c:
        resp = await c.post(TASKS_URL, headers=_headers(), json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_video_task(task_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(f"{TASKS_URL}/{task_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def list_video_tasks(
    *,
    page_num: int = 1,
    page_size: int = 20,
    status: str | None = None,
    model: str | None = None,
    task_ids: list[str] | None = None,
) -> dict:
    params: dict[str, Any] = {"page_num": page_num, "page_size": page_size}
    if status:
        params["filter.status"] = status
    if model:
        params["filter.model"] = model
    if task_ids:
        params["filter.task_ids"] = ",".join(task_ids)

    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.get(TASKS_URL, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


async def delete_video_task(task_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.delete(f"{TASKS_URL}/{task_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json() if resp.content else {}
