"""渐进式提示试点题生成入口（独立于 standard 公共题自动补题）。只读已审核文案，幂等可复跑。"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI
from evals.scenario_quality import grade_scenario
from services.interaction_types import PROGRESSIVE_HINTS, validate_new_interaction_type
from services.public_scenario_service import load_taxonomy
from services.scenario_images import maybe_gen_image
from services.scenario_videos import maybe_gen_video
from utils.id_generator import scenario_id

MANIFEST_PATH = Path(__file__).parent.parent / "data" / "progressive_hint_pilot.yaml"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_EXECUTE_BATCH = 5


def load_manifest() -> list[dict]:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    scenarios = data.get("scenarios") or []
    slugs = [str(s.get("slug", "")) for s in scenarios]
    if len(slugs) != len(set(slugs)):
        raise SystemExit("manifest 存在重复 slug")
    if not scenarios:
        raise SystemExit("manifest 为空")
    return scenarios


def _taxonomy_index() -> dict[str, dict]:
    index = {}
    for domain in load_taxonomy()["domains"]:
        for sub in domain["subs"]:
            index[sub["id"]] = {
                "domainShort": domain["short"],
                "kind": sub["kind"],
                "difficulty": sub["difficulty"],
            }
    return index


def validate_entry(entry: dict, taxonomy: dict[str, dict]) -> list[str]:
    """确定性校验：返回错误列表（空=通过）。含 manifest 结构与 grader 硬规则。"""
    errors: list[str] = []
    slug = str(entry.get("slug", ""))
    if not SLUG_PATTERN.match(slug):
        errors.append(f"slug 非法（小写 kebab-case）：{slug!r}")
    category = entry.get("category") or {}
    sub_id = category.get("subId", "")
    coord = taxonomy.get(sub_id)
    if not coord:
        errors.append(f"subId 不在 taxonomy：{sub_id!r}")
    else:
        if coord["domainShort"] != category.get("domain"):
            errors.append(f"category.domain 与 taxonomy 不符：{category.get('domain')!r}")
        if coord["kind"] != entry.get("kind"):
            errors.append(f"kind 与 taxonomy 不符：manifest={entry.get('kind')!r} taxonomy={coord['kind']!r}")
        if coord["difficulty"] != entry.get("difficulty"):
            errors.append(
                f"difficulty 与 taxonomy 不符："
                f"manifest={entry.get('difficulty')!r} "
                f"taxonomy={coord['difficulty']!r}"
            )
    try:
        validate_new_interaction_type(PROGRESSIVE_HINTS)
    except ValueError as exc:
        errors.append(str(exc))
    candidate = {"interactionType": PROGRESSIVE_HINTS}
    for key in ("kind", "title", "where", "story", "mission", "points", "hints"):
        candidate[key] = entry.get(key)
    for check in grade_scenario(candidate):
        if not check.passed:
            errors.append(f"{check.name}: {check.reason}")
    return errors


def _print_entry(entry: dict, errors: list[str]) -> None:
    """逐题审核表：投放前人工对照本表逐题确认（规格 10.5）。"""
    category = entry.get("category") or {}
    print(f"\n== {entry.get('slug')} [{entry.get('kind')}/{entry.get('difficulty')}] {category.get('subId', '')} ==")
    print(f"  title   : {entry.get('title', '')}")
    print(f"  where   : {entry.get('where', '')}")
    print(f"  story   : {entry.get('story', '')}")
    print(f"  mission : {entry.get('mission', '')}")
    print(f"  points  : {entry.get('points') or []}")
    for i, hint in enumerate(entry.get("hints") or [], 1):
        print(f"  hint{i}  : {hint}")
    print(f"  image   : {entry.get('imagePrompt', '')}")
    if errors:
        for error in errors:
            print(f"  X {error}")
    else:
        print("  OK 硬规则全部通过")


async def cmd_execute(entries: list[dict]) -> None:
    db = AsyncIOMotorClient(MONGO_URI).get_default_database()
    now = datetime.now(timezone.utc)
    for entry in entries:
        slug = str(entry["slug"])
        existing = await db.scenarios.find_one({"slug": slug})
        sid = existing["_id"] if existing else scenario_id()
        link = {"scenarioId": sid, "subId": (entry.get("category") or {}).get("subId", "")}
        image_key = (existing or {}).get("imageKey") or ""
        if not image_key:
            image_key = await maybe_gen_image(sid, entry.get("imagePrompt", ""), link)
        video_key = (existing or {}).get("videoKey") or ""
        if not video_key:
            video_key = await maybe_gen_video(sid, entry.get("videoPrompt") or entry.get("imagePrompt", ""), link)
        doc = {
            "_id": sid,
            "slug": slug,
            "interactionType": PROGRESSIVE_HINTS,
            "category": entry.get("category") or {},
            "kind": entry["kind"],
            "title": entry.get("title", ""),
            "where": entry.get("where", ""),
            "story": entry.get("story", ""),
            "mission": entry.get("mission", ""),
            "points": entry.get("points") or [],
            "hints": entry.get("hints") or [],
            "difficulty": entry.get("difficulty"),
            "imageKey": image_key,
            "imagePrompt": entry.get("imagePrompt", ""),
            "videoKey": video_key,
            "videoPrompt": entry.get("videoPrompt", ""),
            "videoStatus": "ready" if video_key else "skipped",
            "ownerUserId": None,
            "status": "active",
            "createdAt": (existing or {}).get("createdAt") or now,
        }
        await db.scenarios.replace_one({"_id": sid}, doc, upsert=True)
        note = "upsert 复用" if existing else "新建"
        image_note = "有" if image_key else "无"
        video_note = "有" if video_key else "无"
        print(f"  OK {slug} -> scenarioId={sid}（{note}，image={image_note}，video={video_note}）")


async def cmd_archive(entries: list[dict]) -> None:
    db = AsyncIOMotorClient(MONGO_URI).get_default_database()
    for entry in entries:
        slug = str(entry["slug"])
        before = await db.scenarios.find_one({"slug": slug}, {"_id": 1, "status": 1})
        if not before:
            print(f"  !! {slug} 不在库里，跳过")
            continue
        await db.scenarios.update_one({"_id": before["_id"]}, {"$set": {"status": "archived"}})
        print(f"  OK {slug} ({before['_id']}): {before.get('status')!r} -> 'archived'")


def _run_dry_run(manifest: list[dict], by_slug: dict[str, dict], ids: list[str]) -> None:
    missing = [i for i in ids if i not in by_slug]
    if missing:
        raise SystemExit(f"manifest 没有这些 slug：{missing}")
    targets = manifest if not ids else [by_slug[i] for i in ids]
    taxonomy = _taxonomy_index()
    failed = 0
    for entry in targets:
        errors = validate_entry(entry, taxonomy)
        failed += bool(errors)
        _print_entry(entry, errors)
    print(f"\n共 {len(targets)} 道，硬规则通过 {len(targets) - failed} 道，失败 {failed} 道。")
    if failed:
        raise SystemExit(1)



def main() -> None:
    parser = argparse.ArgumentParser(description="渐进式提示试点题：校验 / 入库 / 归档")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只校验并打印，不花钱不写库")
    mode.add_argument("--execute", action="store_true", help="对 --ids 指定题幂等 upsert（每次最多 5 道）")
    mode.add_argument("--archive", action="store_true", help="把 --ids 指定题改为 archived")
    parser.add_argument("--ids", type=str, default="", help="逗号分隔的 slug；dry-run 缺省=全部")
    args = parser.parse_args()

    manifest = load_manifest()
    by_slug = {str(e.get("slug", "")): e for e in manifest}
    ids = [s.strip() for s in args.ids.split(",") if s.strip()]

    if args.dry_run:
        _run_dry_run(manifest, by_slug, ids)
        return

    if not ids:
        raise SystemExit("--execute/--archive 必须用 --ids 显式指定题目")
    unknown = [i for i in ids if i not in by_slug]
    if unknown:
        raise SystemExit(f"manifest 没有这些 slug：{unknown}")
    if args.execute and len(ids) > MAX_EXECUTE_BATCH:
        raise SystemExit(f"每次 --execute 最多 {MAX_EXECUTE_BATCH} 道，10 道试点分两批")

    taxonomy = _taxonomy_index()
    entries = [by_slug[i] for i in ids]
    for entry in entries:
        errors = validate_entry(entry, taxonomy)
        if errors:
            print(f"FAIL {entry.get('slug')} 校验失败：")
            for error in errors:
                print(f"   - {error}")
            raise SystemExit(1)

    if args.execute:
        asyncio.run(cmd_execute(entries))
    else:
        asyncio.run(cmd_archive(entries))


if __name__ == "__main__":
    main()
