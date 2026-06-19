"""按 yaml 坐标系生成公共题（手动跑，用来 bootstrap 或一次性补一波）。

用法（在 server/ 目录）：
    uv run python scripts/generate_public_scenarios.py --dry-run --count 10   # 先看 10 道文案，不生图不入库
    uv run python scripts/generate_public_scenarios.py --count 10             # 真生图入库
    uv run python scripts/generate_public_scenarios.py --count 999            # 跑到所有 sub 达 target

生产线上的自动补题走 `services.scenario_service.topup_public_scenario`，被
`routes/scenarios.py` 的 _maybe_topup 钩子在用户取题时触发，不需要手动跑这个脚本。
这个脚本主要用来：
  1. 本地 dev 一次性 bootstrap 题库
  2. dry-run 检查 prompt 出来的题目质量
  3. 一次性补缺到位（避免依赖用户触发慢慢补）
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import connect_db, get_db
from services.scenario_service import topup_public_scenario, undercovered_subs


async def main(count: int, dry_run: bool) -> None:
    await connect_db()
    db = get_db()

    gaps = await undercovered_subs()
    if not gaps:
        print("所有 sub 都已达 target，无需补题。")
        return

    total_gap = sum(g["gap"] for g in gaps)
    print(f"待补缺口：{len(gaps)} 个 sub，总共 {total_gap} 道题。本次最多生成 {count} 道。")

    generated_ids: set[str] = set() if not dry_run else set()
    created = 0
    for i in range(count):
        # dry-run 时同 sub 不重复选；真跑时入库后 _undercovered_subs 自然不再选
        skip = generated_ids if dry_run else None
        candidates = await undercovered_subs(skip_ids=skip)
        if not candidates:
            print("已无 gap，提前停止。")
            break

        coord = candidates[0]
        print(f"\n[{i+1}/{count}] {coord['domainName']} / {coord['subName']} "
              f"(kind={coord['kind']} d{coord['difficulty']} gap={coord['gap']})")
        try:
            doc = await topup_public_scenario(skip_ids=skip, dry_run=dry_run)
        except Exception as e:
            print(f"  ⚠️ 失败：{e}")
            continue
        if not doc:
            print("  无候选，停止。")
            break

        if dry_run:
            print(f"  → {doc['title']} | {doc['where']}")
            print(f"     story:   {doc['story']}")
            print(f"     mission: {doc['mission']}")
            print(f"     points:  {doc['points']}")
            generated_ids.add(doc["category"]["subId"])
        else:
            print(f"  ✓ {doc['_id']}: {doc['title']}")
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
    args = parser.parse_args()
    asyncio.run(main(args.count, args.dry_run))
