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
POOL_SIZE = 10
REFILL_THRESHOLD = 5

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    "X-DashScope-Async": "enable",
}

# Global image pool
_pool: list[dict] = []
_refilling = False


async def _poll_task(client: httpx.AsyncClient, task_id: str, max_attempts=30):
    for _ in range(max_attempts):
        await asyncio.sleep(2)
        resp = await client.get(
            f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
        )
        data = resp.json()
        status = data.get("output", {}).get("task_status")
        if status == "SUCCEEDED":
            return data["output"]["results"][0]["url"]
        if status == "FAILED":
            raise Exception(data.get("output", {}).get("message", "Generation failed"))
    raise Exception("Image generation timed out")


async def _generate_one():
    topic = random.choice(TOPICS)
    prompt = SCENE_PROMPTS[topic]
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
        return {"imageUrl": image_url, "topic": topic, "prompt": prompt}


async def _fill_pool():
    global _refilling
    _refilling = True
    print(f"[ImagePool] Pool size {len(_pool)}, refilling...")
    while len(_pool) < POOL_SIZE:
        try:
            img = await _generate_one()
            _pool.append(img)
            print(f"[ImagePool] +1 = {len(_pool)}/{POOL_SIZE}")
        except Exception as e:
            print(f"[ImagePool] Generation failed: {e}")
            await asyncio.sleep(10)  # Wait before retry
    print(f"[ImagePool] Full: {len(_pool)}")
    _refilling = False


async def _ensure_pool():
    global _refilling
    if len(_pool) < REFILL_THRESHOLD and not _refilling:
        asyncio.create_task(_fill_pool())


async def init_pool():
    """Call on server startup to pre-fill the pool."""
    if len(_pool) < REFILL_THRESHOLD:
        asyncio.create_task(_fill_pool())


async def get_next_image(user_id: str = "") -> dict:
    """Get the next available image. Returns instantly if pool has images."""
    if _pool:
        img = _pool.pop(0)
        asyncio.create_task(_ensure_pool())
        return img
    # Pool empty — generate on demand
    img = await _generate_one()
    asyncio.create_task(_ensure_pool())
    return img


async def start_prefetch(user_id: str = ""):
    asyncio.create_task(_ensure_pool())
