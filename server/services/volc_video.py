"""火山方舟 Agent Plan 视频任务 API 适配器。"""

import asyncio
import time
from collections.abc import Iterable
from typing import Any

import httpx

from config import (
    VIDEO_API_KEY,
    VIDEO_BASE_URL,
    VIDEO_MODEL,
    VIDEO_POLL_INTERVAL_SECONDS,
    VIDEO_POLL_TIMEOUT_SECONDS,
)
from services.llm_audit import log_video_call

TASKS_URL = f"{VIDEO_BASE_URL}/contents/generations/tasks"

DONE_STATUSES = {"succeeded", "success", "completed", "done"}
FAILED_STATUSES = {"failed", "error", "canceled", "cancelled"}


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {VIDEO_API_KEY}",
        "Content-Type": "application/json",
    }


def _nested_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nested_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nested_values(child)


def _first_string(data: dict, keys: set[str]) -> str:
    for item in _nested_values(data):
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _task_id(data: dict) -> str:
    task_id = _first_string(data, {"id", "task_id", "taskId"})
    if not task_id:
        raise RuntimeError(f"火山方舟视频任务缺少 task id: {data}")
    return task_id


def _status(data: dict) -> str:
    return _first_string(data, {"status", "state"}).lower()


def _video_url(data: dict) -> str:
    return _first_string(data, {"url", "video_url", "videoUrl", "content_url", "result_url"})


async def _create_task(c: httpx.AsyncClient, prompt: str) -> str:
    resp = await c.post(
        TASKS_URL,
        headers=_headers(),
        json={
            "model": VIDEO_MODEL,
            "content": [{"type": "text", "text": prompt}],
        },
    )
    resp.raise_for_status()
    return _task_id(resp.json())


async def _wait_for_video_url(c: httpx.AsyncClient, task_id: str) -> str:
    deadline = time.monotonic() + VIDEO_POLL_TIMEOUT_SECONDS
    last_status = ""
    while time.monotonic() < deadline:
        resp = await c.get(f"{TASKS_URL}/{task_id}", headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        status = _status(data)
        if status:
            last_status = status
        if status in FAILED_STATUSES:
            raise RuntimeError(f"火山方舟视频任务失败: {data}")
        video_url = _video_url(data)
        if status in DONE_STATUSES and video_url:
            return video_url
        await asyncio.sleep(VIDEO_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"火山方舟视频任务超时: {task_id} status={last_status}")


async def video_generate(prompt: str, link_to: dict | None = None) -> bytes:
    """文生视频统一入口。返回 MP4 bytes，调用方负责持久化。"""
    err = None
    video_bytes = b""
    started = time.monotonic()
    task_id = ""
    try:
        async with httpx.AsyncClient(timeout=VIDEO_POLL_TIMEOUT_SECONDS + 60) as c:
            task_id = await _create_task(c, prompt)
            url = await _wait_for_video_url(c, task_id)
            video = await c.get(url)
            video.raise_for_status()
            video_bytes = video.content
            return video_bytes
    except Exception as e:
        err = str(e)
        raise
    finally:
        await log_video_call(
            model=VIDEO_MODEL,
            prompt=prompt,
            metadata={
                "taskId": task_id,
                "durationMs": int((time.monotonic() - started) * 1000),
                "sizeBytes": len(video_bytes),
            },
            link_to=link_to,
            error=err,
        )
