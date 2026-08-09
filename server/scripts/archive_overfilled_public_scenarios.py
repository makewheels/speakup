"""可逆地收缩超过 taxonomy target 的公共题坐标。

默认只 dry-run；显式 `--apply` 才把多余题改为 inactive_duplicate。
不删题、不删历史练习，并可用 `--restore-run <id>` 精确恢复。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import connection
from db.connection import connect_db, get_db
from evals.scenario_quality import grade_scenario, scenario_similarity
from services.public_scenario_service import load_taxonomy


def taxonomy_targets() -> dict[str, int]:
    taxonomy = load_taxonomy()
    default = int(taxonomy.get("target_per_sub", 2))
    return {
        sub["id"]: int(sub.get("target", default))
        for domain in taxonomy["domains"]
        for sub in domain["subs"]
    }


def choose_keep_ids(scenarios: list[dict], target: int, usage: dict[str, int]) -> set[str]:
    if target <= 0:
        return set()

    def quality(doc: dict) -> int:
        return sum(check.passed for check in grade_scenario(doc))

    def created_timestamp(doc: dict) -> float:
        value = doc.get("createdAt")
        return value.timestamp() if hasattr(value, "timestamp") else 0.0

    remaining = list(scenarios)
    remaining.sort(
        key=lambda doc: (usage.get(doc["_id"], 0), quality(doc), created_timestamp(doc)),
        reverse=True,
    )
    selected = [remaining.pop(0)]
    while remaining and len(selected) < target:
        # 有人练过的题优先保留；同等使用量时，选与已保留题最不像的。
        remaining.sort(
            key=lambda doc: (
                usage.get(doc["_id"], 0),
                min(1.0 - scenario_similarity(doc, kept) for kept in selected),
                quality(doc),
                created_timestamp(doc),
            ),
            reverse=True,
        )
        selected.append(remaining.pop(0))
    return {doc["_id"] for doc in selected}


async def usage_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    async for row in get_db().practiceSessions.aggregate([
        {"$match": {"scenarioId": {"$exists": True}, "attempts.0": {"$exists": True}}},
        {"$project": {"scenarioId": 1, "attemptCount": {"$size": "$attempts"}}},
        {"$group": {"_id": "$scenarioId", "count": {"$sum": "$attemptCount"}}},
    ]):
        counts[row["_id"]] = int(row["count"])
    return counts


async def plan_archive() -> list[dict]:
    targets = taxonomy_targets()
    usage = await usage_counts()
    scenarios = await get_db().scenarios.find({
        "ownerUserId": None,
        "status": "active",
        "category.subId": {"$exists": True},
    }).to_list(None)
    grouped: dict[str, list[dict]] = {}
    for doc in scenarios:
        sub_id = (doc.get("category") or {}).get("subId")
        grouped.setdefault(sub_id, []).append(doc)

    plan = []
    for sub_id, docs in sorted(grouped.items()):
        target = targets.get(sub_id)
        if target is None or len(docs) <= target:
            continue
        keep = choose_keep_ids(docs, target, usage)
        archive = [doc for doc in docs if doc["_id"] not in keep]
        plan.append({
            "subId": sub_id,
            "target": target,
            "activeBefore": len(docs),
            "keep": [
                {"id": doc["_id"], "title": doc.get("title", ""), "attempts": usage.get(doc["_id"], 0)}
                for doc in docs if doc["_id"] in keep
            ],
            "archive": [
                {"id": doc["_id"], "title": doc.get("title", ""), "attempts": usage.get(doc["_id"], 0)}
                for doc in archive
            ],
        })
    return plan


async def apply_archive(plan: list[dict], run_id: str) -> int:
    ids = [item["id"] for group in plan for item in group["archive"]]
    if not ids:
        return 0
    now = datetime.now(timezone.utc)
    result = await get_db().scenarios.update_many(
        {"_id": {"$in": ids}, "ownerUserId": None, "status": "active"},
        {"$set": {
            "status": "inactive_duplicate",
            "archivedAt": now,
            "archivedReason": "overfilled_sub",
            "archiveRunId": run_id,
        }},
    )
    return int(result.modified_count)


async def restore_run(run_id: str) -> int:
    result = await get_db().scenarios.update_many(
        {"archiveRunId": run_id, "status": "inactive_duplicate"},
        {
            "$set": {"status": "active"},
            "$unset": {"archivedAt": "", "archivedReason": "", "archiveRunId": ""},
        },
    )
    return int(result.modified_count)


async def async_main(args: argparse.Namespace) -> int:
    await connect_db()
    try:
        if args.restore_run:
            restored = await restore_run(args.restore_run)
            print(json.dumps({"restoreRun": args.restore_run, "restored": restored}, ensure_ascii=False))
            return 0

        plan = await plan_archive()
        summary = {
            "mode": "apply" if args.apply else "dry-run",
            "overfilledSubs": len(plan),
            "archiveCount": sum(len(group["archive"]) for group in plan),
            "plan": plan,
        }
        if args.apply:
            run_id = datetime.now(timezone.utc).strftime("scenario-dedupe-%Y%m%dT%H%M%SZ")
            summary["archiveRunId"] = run_id
            summary["modified"] = await apply_archive(plan, run_id)
        print(json.dumps(summary, ensure_ascii=False, default=str, indent=2))
        return 0
    finally:
        if connection.client is not None:
            connection.client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive public scenarios above taxonomy target")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="apply the reviewed archive plan")
    mode.add_argument("--restore-run", help="restore exactly one previous archiveRunId")
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
