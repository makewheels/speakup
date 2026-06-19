"""LLM/图片调用成本报表：从 llmCalls 审计表按天 / 按 kind / 按模型汇总花了多少钱。

用法（server/ 目录）：
    uv run python scripts/cost_report.py              # 全部汇总
    uv run python scripts/cost_report.py --days 7     # 只看最近 7 天
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import connect_db, get_db


def _fmt(cost: float) -> str:
    return f"¥{cost:.4f}"


async def main(days: int | None) -> None:
    await connect_db()
    db = get_db()

    match: dict = {}
    if days:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        match = {"createdAt": {"$gte": since}}
        print(f"== 最近 {days} 天 ==\n")
    else:
        print("== 全部历史 ==\n")

    total_docs = await db.llmCalls.count_documents(match)
    if total_docs == 0:
        print("llmCalls 没有记录。")
        return

    # 总计
    agg_total = await db.llmCalls.aggregate([
        {"$match": match},
        {"$group": {
            "_id": None,
            "cost": {"$sum": "$cost"},
            "n": {"$sum": 1},
            "promptTok": {"$sum": "$tokens.prompt"},
            "completionTok": {"$sum": "$tokens.completion"},
            "errors": {"$sum": {"$cond": [{"$ne": ["$error", None]}, 1, 0]}},
        }},
    ]).to_list(1)
    t = agg_total[0]
    print(f"总调用 {t['n']} 次，总成本 {_fmt(t['cost'])}，失败 {t['errors']} 次")
    print(f"  文本 tokens: prompt {t['promptTok']:,} / completion {t['completionTok']:,}\n")

    # 按 kind
    print("— 按 kind —")
    async for d in db.llmCalls.aggregate([
        {"$match": match},
        {"$group": {"_id": "$kind", "cost": {"$sum": "$cost"}, "n": {"$sum": 1}}},
        {"$sort": {"cost": -1}},
    ]):
        avg = d["cost"] / d["n"] if d["n"] else 0
        print(f"  {d['_id']:<26} {d['n']:>4} 次  {_fmt(d['cost']):>12}  (均 {_fmt(avg)}/次)")

    # 按模型
    print("\n— 按模型 —")
    async for d in db.llmCalls.aggregate([
        {"$match": match},
        {"$group": {"_id": "$model", "cost": {"$sum": "$cost"}, "n": {"$sum": 1}}},
        {"$sort": {"cost": -1}},
    ]):
        print(f"  {d['_id']:<26} {d['n']:>4} 次  {_fmt(d['cost']):>12}")

    # 按天
    print("\n— 按天 —")
    async for d in db.llmCalls.aggregate([
        {"$match": match},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
            "cost": {"$sum": "$cost"},
            "n": {"$sum": 1},
        }},
        {"$sort": {"_id": -1}},
        {"$limit": 30},
    ]):
        print(f"  {d['_id']}  {d['n']:>4} 次  {_fmt(d['cost']):>12}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="只统计最近 N 天")
    args = parser.parse_args()
    asyncio.run(main(args.days))
