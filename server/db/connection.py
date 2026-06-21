from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    db = client.get_default_database()
    await client.admin.command("ping")
    print("MongoDB connected")


def get_db():
    return db
