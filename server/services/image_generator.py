import asyncio
import random
import httpx
from config import DASHSCOPE_API_KEY

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"

SCENE_PROMPTS = {
    "daily": "A bright, photorealistic everyday life scene in a kitchen or dining room. Multiple people cooking, eating, or talking. Rich details: utensils, food, windows, plants. No text.",
    "travel": "A bright, photorealistic travel scene at an airport check-in counter or hotel lobby. Travelers with luggage, staff at desks, information screens. No text.",
    "nature": "A vibrant, photorealistic nature scene in a park or garden. People walking dogs, children playing, trees, flowers, birds. Clear actions visible. No text.",
    "social": "A lively, photorealistic social scene at a restaurant or cafe. People chatting at tables, waiter serving, food and drinks on tables. Warm atmosphere. No text.",
    "home": "A cozy, photorealistic home scene in a living room or bedroom. Family members relaxing, reading, playing. Furniture, books, lamps visible. No text.",
    "city": "A bustling, photorealistic city scene: busy street with shops, pedestrians crossing, outdoor market stalls, bus or subway entrance. No text.",
}

TOPICS = list(SCENE_PROMPTS.keys())

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    "X-DashScope-Async": "enable",
}


async def _poll_task(client: httpx.AsyncClient, task_id: str, max_attempts=30):
    for _ in range(max_attempts):
        await asyncio.sleep(2)
        resp = await client.get(f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"})
        data = resp.json()
        status = data.get("output", {}).get("task_status")
        if status == "SUCCEEDED":
            return data["output"]["results"][0]["url"]
        if status == "FAILED":
            raise Exception(data.get("output", {}).get("message", "Image generation failed"))
    raise Exception("Image generation timed out")


async def _generate_one(topic=None):
    t = topic or random.choice(TOPICS)
    prompt = SCENE_PROMPTS[t]

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(DASHSCOPE_URL, headers=HEADERS, json={
            "model": "wanx-v1",
            "input": {"prompt": prompt},
            "parameters": {"size": "1024*1024", "n": 1},
        })
        data = resp.json()
        if data.get("code"):
            raise Exception(data.get("message", "Generation failed"))

        task_id = data["output"]["task_id"]
        image_url = await _poll_task(client, task_id)
        return {"imageUrl": image_url, "topic": t, "prompt": prompt}


# Image cache
_cache: dict[str, dict] = {}
_pending: dict[str, asyncio.Task] = {}


async def get_next_image(user_id: str) -> dict:
    cached = _cache.pop(user_id, None)
    if cached:
        asyncio.create_task(_prefetch(user_id))
        return cached

    if user_id in _pending:
        await _pending[user_id]
        cached = _cache.pop(user_id, None)
        if cached:
            asyncio.create_task(_prefetch(user_id))
            return cached

    result = await _generate_one()
    asyncio.create_task(_prefetch(user_id))
    return result


async def _prefetch(user_id: str):
    if user_id in _pending or user_id in _cache:
        return
    task = asyncio.create_task(_generate_one())

    def _done(t):
        if not t.exception():
            _cache[user_id] = t.result()
        _pending.pop(user_id, None)

    task.add_done_callback(_done)
    _pending[user_id] = task


async def start_prefetch(user_id: str):
    await _prefetch(user_id)
