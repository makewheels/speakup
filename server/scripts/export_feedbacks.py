"""导出全量用户反馈（产品方排查用）。

用法：
  uv run python -m scripts.export_feedbacks
"""
import asyncio
import json
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI


async def main() -> int:
    client = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    db = client.get_default_database()
    docs = []
    async for f in db.feedbacks.find().sort("createdAt", -1):
        f["_id"] = str(f["_id"])
        for k, v in list(f.items()):
            if hasattr(v, "isoformat"):
                f[k] = v.isoformat()
        docs.append(f)
    client.close()
    print(json.dumps(docs, ensure_ascii=False, indent=2))
    print(f"\n共 {len(docs)} 条反馈", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
