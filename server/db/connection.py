from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    db = client.get_default_database()
    await client.admin.command("ping")
    await db.practiceAttempts.create_index(
        [("practiceId", 1), ("round", 1)], unique=True, name="practice_round_unique"
    )
    await db.practiceAttempts.create_index(
        [("userId", 1), ("createdAt", -1)], name="user_attempt_history"
    )
    print("MongoDB connected")


def get_db():
    return db
