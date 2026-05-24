import random

SCENE_PROMPTS = {
    "daily": "A bright, photorealistic everyday life scene in a kitchen or dining room. Multiple people cooking, eating, or talking. Rich details: utensils, food, windows, plants. No text.",
    "travel": "A bright, photorealistic travel scene at an airport check-in counter or hotel lobby. Travelers with luggage, staff at desks, information screens. No text.",
    "nature": "A vibrant, photorealistic nature scene in a park or garden. People walking dogs, children playing, trees, flowers, birds. Clear actions visible. No text.",
    "social": "A lively, photorealistic social scene at a restaurant or cafe. People chatting at tables, waiter serving, food and drinks on tables. Warm atmosphere. No text.",
    "home": "A cozy, photorealistic home scene in a living room or bedroom. Family members relaxing, reading, playing. Furniture, books, lamps visible. No text.",
    "city": "A bustling, photorealistic city scene: busy street with shops, pedestrians crossing, outdoor market stalls, bus or subway entrance. No text.",
}

QUERIES = {
    "daily": "kitchen,cooking,food",
    "travel": "airport,hotel,travel",
    "nature": "park,garden,forest",
    "social": "restaurant,cafe,people",
    "home": "living-room,bedroom,cozy",
    "city": "city,street,market",
}

TOPICS = list(SCENE_PROMPTS.keys())


async def get_next_image(user_id: str = "") -> dict:
    topic = random.choice(TOPICS)
    query = QUERIES[topic]
    url = f"https://loremflickr.com/1024/1024/{query}?random={random.randint(1,99999)}"
    return {
        "imageUrl": url,
        "topic": topic,
        "prompt": SCENE_PROMPTS[topic],
    }


async def start_prefetch(user_id: str = ""):
    pass


async def init_pool():
    pass
