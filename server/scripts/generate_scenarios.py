"""预生成场景题库：万相生图 → OSS files → scenarios 集合。

用法（在 server/ 目录）：
    uv run python scripts/generate_scenarios.py            # 生成内置 3 个场景
    uv run python scripts/generate_scenarios.py --dry-run  # 只看场景文案，不调 API

题目全局共享、与用户解耦；重复跑会按 slug 跳过已存在的场景。
"""

import argparse
import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import connect_db, get_db
from services.oss_storage import upload_bytes_async
from services.wanx import PHOTO_STYLE as STYLE, WANX_MODEL, wanx_generate
from utils.id_generator import file_id, scenario_id

SCENARIOS = [
    {
        "slug": "coffee-wrong-order",
        "where": "☕️ 咖啡店 · 西雅图",
        "story": "你点的是热拿铁，店员却给了你一杯冰美式，而你的航班 1 小时后就起飞了。",
        "mission": "让店员重做，并让他知道你赶时间。",
        "difficulty": 1,
        "imagePrompt": f"busy specialty coffee shop counter, a clear plastic cup of iced americano "
                       f"with a receipt beside it on the pickup counter, barista working in background, {STYLE}",
    },
    {
        "slug": "hotel-no-reservation",
        "where": "🏨 酒店前台 · 深夜",
        "story": "你深夜抵达酒店，前台说系统里查不到你的预订，但你手机里有确认邮件。",
        "mission": "出示证据，让前台无论如何给你安排今晚的房间。",
        "difficulty": 2,
        "imagePrompt": f"hotel front desk late at night, receptionist behind the counter looking at "
                       f"a computer screen with a concerned expression, warm lobby lighting, "
                       f"a suitcase in the foreground, {STYLE}",
    },
    {
        "slug": "landlord-heating",
        "where": "📞 打给房东 · 你的公寓",
        "story": "公寓暖气坏了三天，外面零下，房东一直说'再看看'拖着不修。",
        "mission": "电话里要求房东本周内必须修好，并问清楚不修怎么办。",
        "difficulty": 3,
        "imagePrompt": f"apartment living room in winter, person's hand touching a cold radiator under "
                       f"a frosted window, breath visible in cold indoor air, blanket on sofa, {STYLE}",
    },
]

async def main(dry_run: bool) -> None:
    if dry_run:
        for s in SCENARIOS:
            print(f"[{s['slug']}] {s['where']}\n  情境: {s['story']}\n  任务: {s['mission']}\n")
        return

    await connect_db()
    db = get_db()
    for s in SCENARIOS:
        if await db.scenarios.find_one({"slug": s["slug"]}):
            print(f"跳过已存在: {s['slug']}")
            continue

        print(f"生成中: {s['slug']} …")
        data = await wanx_generate(s["imagePrompt"])

        fid = file_id()
        key = f"files/{fid}/orig.jpg"
        oss_url = await upload_bytes_async(key, data, "image/jpeg")
        now = datetime.now(timezone.utc)
        await db.files.insert_one({
            "_id": fid,
            "md5": hashlib.md5(data).hexdigest(),
            "mimeType": "image/jpeg",
            "source": WANX_MODEL,
            "sourceUrl": "",
            "topic": s["slug"],
            "variants": {"orig": {"key": key, "url": oss_url, "bytes": len(data)}},
            "status": "active",
            "createdAt": now,
        })

        await db.scenarios.insert_one({
            "_id": scenario_id(),
            "slug": s["slug"],
            "where": s["where"],
            "story": s["story"],
            "mission": s["mission"],
            "difficulty": s["difficulty"],
            "imageFileId": fid,
            "imagePrompt": s["imagePrompt"],
            "status": "active",
            "createdAt": now,
        })
        print(f"完成: {s['slug']} → file {fid} ({len(data) // 1024} KB)")

    total = await db.scenarios.count_documents({"status": "active"})
    print(f"题库现有 {total} 个场景")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args().dry_run))
