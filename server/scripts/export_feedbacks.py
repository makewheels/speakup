"""导出真实用户反馈（产品方排查用）。

用法：
  uv run python -m scripts.export_feedbacks
  uv run python -m scripts.export_feedbacks --include-ai-test
"""
import argparse
import asyncio
import json
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出用户反馈，默认排除自动体验数据")
    parser.add_argument(
        "--include-ai-test",
        action="store_true",
        help="同时导出 sourceType=ai_test 的自动体验反馈",
    )
    return parser.parse_args()


async def main(*, include_ai_test: bool = False) -> int:
    client = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
    db = client.get_default_database()
    docs = []
    query = {} if include_ai_test else {"sourceType": {"$ne": "ai_test"}}
    async for f in db.feedbacks.find(query).sort("createdAt", -1):
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
    args = _parse_args()
    raise SystemExit(asyncio.run(main(include_ai_test=args.include_ai_test)))
