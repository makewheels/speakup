"""预生成场景题库：万相生图 → OSS → scenarios 集合。

用法（在 server/ 目录）：
    uv run python scripts/generate_scenarios.py            # 生成内置题库
    uv run python scripts/generate_scenarios.py --dry-run  # 只看场景文案，不调 API

题目全局共享、与用户解耦；重复跑会按 slug 跳过已存在的场景。

kind 分类（对齐雅思 Part1/2/3 + 实用口语）：
  task     办事交涉   — 看场景+冲突，开口解决（礼貌度、是否达成）
  chat     日常问答   — 雅思 P1 / 街头采访，回答关于自己的小问题
  describe 描述长谈   — 雅思 P2 / vlog，对镜头讲一段（人/地/经历/物）
  opinion  观点表达   — 雅思 P3 / 采访，对话题表态并说理由
  explain  讲解科普   — TED / 科普，把一件事讲清楚给别人
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import connect_db, get_db
from services.oss_storage import upload_bytes_async
from services.scenario_service import scenario_image_key
from services.wanx import PHOTO_STYLE as STYLE, wanx_generate
from utils.id_generator import scenario_id

SCENARIOS = [
    # ── 办事交涉 task ──
    {
        "slug": "coffee-wrong-order", "kind": "task", "title": "咖啡店给错咖啡",
        "where": "☕️ 咖啡店 · 西雅图",
        "story": "你点的是热拿铁，店员却给了你一杯冰美式，而你的航班 1 小时后就起飞了。",
        "mission": "让店员重做，并让他知道你赶时间。", "difficulty": 1,
        "imagePrompt": f"busy specialty coffee shop counter, a clear plastic cup of iced americano "
                       f"with a receipt beside it on the pickup counter, barista working in background, {STYLE}",
    },
    {
        "slug": "book-doctor", "kind": "task", "title": "打电话预约看医生",
        "where": "🏥 打给社区诊所",
        "story": "你这两天嗓子疼、有点发烧，想约这周看医生，但诊所说本周很满。",
        "mission": "说清楚症状、争取尽早的号，并问清要不要带什么。", "difficulty": 2,
        "imagePrompt": f"a person at home holding a phone to their ear, a wall calendar and a box of "
                       f"medicine and a thermometer on the table, soft daylight, making a clinic appointment, {STYLE}",
    },
    {
        "slug": "ask-for-raise", "kind": "task", "title": "跟老板申请加薪",
        "where": "💼 一对一会议室",
        "story": "你过去一年扛下了好几个项目，但工资两年没动。你约了老板单独聊。",
        "mission": "摆出你的贡献，提出具体的加薪数字，并应对'再考虑考虑'。", "difficulty": 3,
        "imagePrompt": f"a modern office meeting room, two chairs facing each other across a small table, "
                       f"a laptop and a notepad on the table, professional natural daylight, one-on-one meeting, {STYLE}",
    },
    {
        "slug": "assign-tasks", "kind": "task", "title": "给实习生布置任务",
        "where": "📋 工位 · 周一早会",
        "story": "新来的实习生今天第一天，这周有三件事要交给他做。",
        "mission": "把这周的任务讲清楚：做什么、优先级、什么时候交、有问题找谁。", "difficulty": 2,
        "imagePrompt": f"an office desk with a whiteboard listing a few tasks, sticky notes, a laptop open to "
                       f"a project board, two coffee cups, collaborative workspace, morning light, {STYLE}",
    },
    {
        "slug": "flight-cancelled", "kind": "task", "title": "航班取消争取改签",
        "where": "🧳 机场服务台 · 深夜",
        "story": "你的航班被取消了，明天一早有重要会议，服务台前还排着长队。",
        "mission": "争取改签到最早的航班，并要求安排今晚的酒店。", "difficulty": 3,
        "imagePrompt": f"airline service desk at an airport at night, a departures board showing a cancelled "
                       f"flight in the background, a suitcase in the foreground, tired travelers waiting, {STYLE}",
    },
    # ── 日常问答 chat（雅思 P1 / 街头采访）──
    {
        "slug": "intro-hometown", "kind": "chat", "title": "介绍你的家乡",
        "where": "🎤 街头采访",
        "story": "一个外国博主在街上随机采访你，想了解中国的城市。",
        "mission": "用英语介绍你的家乡：在哪、什么样、你最喜欢它什么。", "difficulty": 1,
        "imagePrompt": f"a person being interviewed on a lively city street, a microphone with a small logo cube "
                       f"held toward the camera, blurred pedestrians and shops behind, vlog street interview vibe, {STYLE}",
    },
    {
        "slug": "phone-habits", "kind": "chat", "title": "聊聊你怎么用手机",
        "where": "🎤 街头采访",
        "story": "街访话题：现代人离不开手机。轮到你了。",
        "mission": "说说你每天怎么用手机和社交媒体，花多少时间，觉得好还是不好。", "difficulty": 1,
        "imagePrompt": f"close-up of hands holding a smartphone showing colorful social media app icons, "
                       f"a cafe table and coffee in the background, casual daily life, {STYLE}",
    },
    # ── 描述长谈 describe（雅思 P2 / vlog）──
    {
        "slug": "memorable-trip", "kind": "describe", "title": "讲讲难忘的旅行",
        "where": "🎥 拍 vlog",
        "story": "你在拍一条旅行 vlog，对着镜头跟观众聊。",
        "mission": "讲一次你最难忘的旅行：去了哪、和谁、发生了什么、为什么难忘。", "difficulty": 2,
        "imagePrompt": f"first-person vlog setup, a smartphone on a small tripod facing outward at a scenic "
                       f"travel viewpoint, mountains and open sky in the background, sunny, {STYLE}",
    },
    {
        "slug": "influential-person", "kind": "describe", "title": "影响你最深的人",
        "where": "🎥 对着镜头",
        "story": "你想录一段，聊聊一个改变了你的人。",
        "mission": "描述一个对你影响很大的人：是谁、什么样的人、怎么影响了你。", "difficulty": 2,
        "imagePrompt": f"a warm cozy room with a framed photo standing on a wooden desk, soft window light, "
                       f"a cup of tea, reflective nostalgic mood, {STYLE}",
    },
    {
        "slug": "meaningful-gift", "kind": "describe", "title": "一件难忘的礼物",
        "where": "🎁 聊聊收到的礼物",
        "story": "朋友问你收到过最有意义的礼物是什么。",
        "mission": "描述一件你收到的、很有意义的礼物：是什么、谁送的、为什么特别。", "difficulty": 2,
        "imagePrompt": f"a thoughtfully wrapped gift box opened on a wooden table, ribbon and a handwritten "
                       f"card beside it, warm soft light, {STYLE}",
    },
    # ── 观点表达 opinion（雅思 P3 / 采访）──
    {
        "slug": "remote-work", "kind": "opinion", "title": "你怎么看远程办公",
        "where": "🗣️ 观点采访",
        "story": "采访话题：越来越多公司允许在家办公。",
        "mission": "说说你支持还是反对远程办公，给出至少两个理由。", "difficulty": 3,
        "imagePrompt": f"a tidy home office desk with a laptop showing a video call, coffee, a small plant, "
                       f"natural daylight from a window, remote work setting, {STYLE}",
    },
    {
        "slug": "env-action", "kind": "opinion", "title": "为环保你能做什么",
        "where": "🗣️ 观点采访",
        "story": "采访话题：环保不只是政府的事。",
        "mission": "说说普通人能为环保做些什么，你自己做了哪些。", "difficulty": 3,
        "imagePrompt": f"a reusable cloth shopping bag full of fresh vegetables, a bicycle leaning on a wall, "
                       f"recycling bins nearby, bright eco-friendly daily street scene, {STYLE}",
    },
    # ── 讲解科普 explain（TED / 科普）──
    {
        "slug": "spring-festival", "kind": "explain", "title": "讲讲春节为什么回家",
        "where": "🥟 讲给外国朋友",
        "story": "外国朋友很好奇：为什么中国人过年一定要回家？",
        "mission": "把春节回家团聚这件事讲清楚：是什么、为什么重要、大家会做什么。", "difficulty": 2,
        "imagePrompt": f"a festive Chinese New Year family reunion dinner table full of dishes, red lanterns "
                       f"and decorations in the background, warm celebratory atmosphere, {STYLE}",
    },
]


async def main(dry_run: bool) -> None:
    if dry_run:
        for s in SCENARIOS:
            print(f"[{s['kind']}] {s['title']} · {s['where']}（难度{s['difficulty']}）\n  任务: {s['mission']}\n")
        print(f"共 {len(SCENARIOS)} 个场景")
        return

    await connect_db()
    db = get_db()
    for s in SCENARIOS:
        if await db.scenarios.find_one({"slug": s["slug"]}):
            print(f"跳过已存在: {s['slug']}")
            continue

        print(f"生成中: {s['slug']} …")
        image = await wanx_generate(s["imagePrompt"])

        sid = scenario_id()
        key = scenario_image_key(sid)
        await upload_bytes_async(key, image, "image/jpeg")
        await db.scenarios.insert_one({
            "_id": sid,
            "slug": s["slug"],
            "kind": s["kind"],
            "title": s["title"],
            "where": s["where"],
            "story": s["story"],
            "mission": s["mission"],
            "difficulty": s["difficulty"],
            "imageKey": key,
            "imagePrompt": s["imagePrompt"],
            "status": "active",
            "createdAt": datetime.now(timezone.utc),
        })
        print(f"完成: {s['slug']} → {key} ({len(image) // 1024} KB)")

    total = await db.scenarios.count_documents({"status": "active"})
    print(f"题库现有 {total} 个场景")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args().dry_run))
