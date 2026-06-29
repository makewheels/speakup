"""给已有场景补生成视频。

默认 dry-run，只打印会处理哪些场景；真写入需要 --execute 且 VIDEO_ENABLED=true。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import connect_db, get_db
from services import scenario_videos


def _query(scenario_id: str = "") -> dict:
    query = {"status": "active", "videoKey": {"$in": [None, ""]}}
    if scenario_id:
        query["_id"] = scenario_id
    return query


async def _candidate_docs(limit: int, scenario_id: str = "") -> list[dict]:
    cursor = get_db().scenarios.find(_query(scenario_id)).sort("createdAt", -1).limit(limit)
    return await cursor.to_list(limit)


async def _backfill_one(doc: dict, execute: bool) -> str:
    prompt = doc.get("videoPrompt") or doc.get("imagePrompt") or ""
    sid = doc["_id"]
    if not prompt:
        return "skip:no-prompt"
    if not execute:
        return "dry-run"
    key = await scenario_videos.maybe_gen_video(sid, prompt, {"scenarioId": sid})
    status = "ready" if key else "skipped"
    await get_db().scenarios.update_one(
        {"_id": sid},
        {"$set": {"videoKey": key, "videoPrompt": prompt, "videoStatus": status}},
    )
    return status


async def main(limit: int, execute: bool, scenario_id: str) -> None:
    await connect_db()
    docs = await _candidate_docs(limit, scenario_id)
    if execute and not scenario_videos.VIDEO_ENABLED:
        print("VIDEO_ENABLED=false，拒绝真生成。请先在 env 中设 VIDEO_ENABLED=true。")
        return
    if not docs:
        print("没有需要补视频的 active 场景。")
        return
    for i, doc in enumerate(docs, start=1):
        status = await _backfill_one(doc, execute)
        print(f"[{i}/{len(docs)}] {doc['_id']} {doc.get('title', '')}: {status}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--scenario-id", default="")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.execute, args.scenario_id))
