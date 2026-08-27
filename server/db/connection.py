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
    # 开始动作幂等键：只覆盖非空 creationRequestId，旧客户端缺省该字段不受影响
    await db.practiceSessions.create_index(
        [("userId", 1), ("creationRequestId", 1)],
        unique=True,
        name="session_creation_idempotent",
        partialFilterExpression={"creationRequestId": {"$exists": True}},
    )
    print("MongoDB connected")


def get_db():
    return db
