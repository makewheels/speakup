"""通义万相 wanx-v1 文生图（DashScope 异步任务接口）。"""

import asyncio

import httpx

from config import DASHSCOPE_API_KEY

SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

PHOTO_STYLE = (
    "realistic photograph, natural lighting, shot on 35mm, candid documentary style, "
    "first-person customer point of view, no text, no watermark"
)


async def wanx_generate(prompt: str, size: str = "1280*720") -> bytes:
    """提交异步生图任务，轮询直到完成，返回图片字节。约 20~60 秒。"""
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}
    async with httpx.AsyncClient(timeout=60.0) as c:
        resp = await c.post(
            SUBMIT_URL,
            headers={**headers, "X-DashScope-Async": "enable"},
            json={
                "model": "wanx-v1",
                "input": {"prompt": prompt},
                "parameters": {"size": size, "n": 1},
            },
        )
        resp.raise_for_status()
        task_id = resp.json()["output"]["task_id"]

        for _ in range(60):
            await asyncio.sleep(5)
            r = await c.get(TASK_URL.format(task_id=task_id), headers=headers)
            r.raise_for_status()
            output = r.json()["output"]
            status = output["task_status"]
            if status == "SUCCEEDED":
                img = await c.get(output["results"][0]["url"])
                img.raise_for_status()
                return img.content
            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(f"万相任务失败: {output}")
        raise TimeoutError("万相任务超时（5 分钟）")
