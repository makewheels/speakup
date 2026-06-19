"""按 yaml 坐标系生成公共题（手动跑，用来 bootstrap 或一次性补一波）。

用法（在 server/ 目录）：
    uv run python scripts/generate_public_scenarios.py --dry-run --count 10           # 先看 10 道文案
    uv run python scripts/generate_public_scenarios.py --count 10                     # 真生图入库
    uv run python scripts/generate_public_scenarios.py --count 999                    # 跑到所有 sub 达 target
    uv run python scripts/generate_public_scenarios.py --dry-run --sub-id A,B         # 指定 sub 测试 prompt 改动效果

生产线上的自动补题走 `services.scenario_service.topup_public_scenario`，被
`routes/scenarios.py` 的 _maybe_topup 钩子在用户取题时触发，不需要手动跑这个脚本。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import connect_db, get_db
from services.scenario_service import (
    _llm_spec_for_coord,
    load_taxonomy,
    topup_public_scenario,
    undercovered_subs,
)


async def _run_specific_subs(sub_ids: list[str], dry_run: bool) -> int:
    """指定 sub 跑（用于改 prompt 后对比 / 重新生成已有 sub 的题）。
    dry_run=True 只打文案，不入库不调万相。"""
    tax = load_taxonomy()
    coord_by_id = {}
    for d in tax["domains"]:
        for s in d["subs"]:
            coord_by_id[s["id"]] = {
                "domainName": d["domain"],
                "domainShort": d["short"],
                "subId": s["id"],
                "subName": s["sub"],
                "kind": s["kind"],
                "difficulty": s["difficulty"],
                "note": s.get("note", ""),
                "bonusZh": s.get("bonus_zh", False),
            }
    created = 0
    for i, sid in enumerate(sub_ids):
        coord = coord_by_id.get(sid)
        if not coord:
            print(f"  ⚠️ 未知 sub-id: {sid}（看 yaml 里的 id 字段）")
            continue
        print(f"\n[{i+1}/{len(sub_ids)}] {coord['domainName']} / {coord['subName']} "
              f"(kind={coord['kind']} d{coord['difficulty']})")
        try:
            spec = await _llm_spec_for_coord(coord)
        except Exception as e:
            print(f"  ⚠️ 失败：{e}")
            continue
        print(f"  → {spec.get('title')} | {spec.get('where')}")
        print(f"     story:   {spec.get('story')}")
        print(f"     mission: {spec.get('mission')}")
        print(f"     points:  {spec.get('points')}")
        if not dry_run:
            print("  （真生成模式 --sub-id 暂不支持入库，先 dry-run 验证）")
        created += 1
    return created


async def main(count: int, dry_run: bool, sub_ids: list[str] | None) -> None:
    await connect_db()

    if sub_ids:
        await _run_specific_subs(sub_ids, dry_run=True)  # 强制 dry-run 安全
        return

    db = get_db()
    gaps = await undercovered_subs()
    if not gaps:
        print("所有 sub 都已达 target，无需补题。")
        return

    total_gap = sum(g["gap"] for g in gaps)
    print(f"待补缺口：{len(gaps)} 个 sub，总共 {total_gap} 道题。本次最多生成 {count} 道。")

    generated_ids: set[str] = set()
    created = 0
    for i in range(count):
        # dry-run 时同 sub 不重复选；真跑时入库后 undercovered_subs 自然不再选
        skip = generated_ids if dry_run else None
        try:
            doc = await topup_public_scenario(skip_ids=skip, dry_run=dry_run)
        except Exception as e:
            print(f"  ⚠️ 失败：{e}")
            continue
        if not doc:
            print("已无 gap，提前停止。")
            break

        sub_id = doc["category"]["subId"]
        generated_ids.add(sub_id)
        print(f"\n[{i+1}/{count}] subId={sub_id} kind={doc['kind']} d{doc['difficulty']}")
        if dry_run:
            print(f"  → {doc['title']} | {doc['where']}")
            print(f"     story:   {doc['story']}")
            print(f"     mission: {doc['mission']}")
            print(f"     points:  {doc['points']}")
        else:
            print(f"  ✓ {doc['_id']}: {doc['title']} | {doc['where']}")
        created += 1

    if not dry_run:
        total = await db.scenarios.count_documents(
            {"ownerUserId": None, "status": "active"}
        )
        print(f"\n本次新建 {created} 道，公共池现有 {total} 道 active。")
    else:
        print(f"\n— dry-run 完成，{created} 道文案打印（未入库未生图）—")
        print("文案 OK 后去掉 --dry-run 跑真生成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10, help="本次最多生成几道")
    parser.add_argument("--dry-run", action="store_true",
                        help="只跑 LLM 看文案，不调万相、不入库")
    parser.add_argument("--sub-id", type=str, default="",
                        help="指定 sub.id 只跑这几个（逗号分隔），强制 dry-run")
    args = parser.parse_args()
    sub_ids = [s.strip() for s in args.sub_id.split(",") if s.strip()] if args.sub_id else None
    asyncio.run(main(args.count, args.dry_run, sub_ids))
