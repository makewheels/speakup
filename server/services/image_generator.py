import random

QUERIES = {
    "daily": "kitchen,cooking,food",
    "travel": "airport,hotel,travel",
    "nature": "park,garden,forest",
    "social": "restaurant,cafe,people",
    "home": "living-room,bedroom,cozy",
    "city": "city,street,market",
}

TOPICS = list(QUERIES.keys())


async def get_next_image() -> dict:
    topic = random.choice(TOPICS)
    url = f"https://loremflickr.com/640/640/{QUERIES[topic]}?random={random.randint(1, 99999)}"
    return {"imageUrl": url, "topic": topic}
