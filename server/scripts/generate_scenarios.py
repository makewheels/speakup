"""预生成场景题库：万相生图 → OSS → scenarios 集合。

用法（在 server/ 目录）：
    uv run python scripts/generate_scenarios.py            # 新题生图入库；已存在的只同步文案（不重生图）
    uv run python scripts/generate_scenarios.py --dry-run  # 只看场景文案，不调 API

题目全局共享、与用户解耦。本脚本是题库文案的来源（source of truth）：
改了 title/where/story/mission/points/difficulty 后重跑，会就地更新已有题目的文案，图片不动、不花钱。

kind 分类（对齐雅思 Part1/2/3 + 实用口语）：
  task     办事交涉   — 看场景+冲突，开口解决
  chat     日常问答   — 雅思 P1 / 街头采访
  describe 描述长谈   — 雅思 P2 / vlog
  opinion  观点表达   — 雅思 P3 / 采访
  explain  讲解科普   — TED / 科普

points = 要让用户用英语说出来的具体内容：
  办事/讲解类给死内容（用户只管翻译表达，不用自己编剧情）；
  日常/描述/观点类给提示要点（内容是用户自己的，给个框架）。
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

TEXT_FIELDS = ("kind", "title", "where", "story", "mission", "points", "difficulty")

SCENARIOS = [
    # ── 办事交涉 task（给死内容）──
    {
        "slug": "coffee-wrong-order", "kind": "task", "title": "咖啡店给错咖啡",
        "where": "☕️ 咖啡店 · 西雅图",
        "story": "你点的是热拿铁，店员却给了你一杯冰美式，而你的航班 1 小时后就起飞了。",
        "mission": "让店员重做，并让他知道你赶时间。", "difficulty": 1,
        "points": [
            "说明你点的是热拿铁，但拿到的是冰美式",
            "请他重做一杯热拿铁",
            "说你赶飞机，能不能快一点",
        ],
        "imagePrompt": f"busy specialty coffee shop counter, a clear plastic cup of iced americano "
                       f"with a receipt beside it on the pickup counter, barista working in background, {STYLE}",
    },
    {
        "slug": "book-doctor", "kind": "task", "title": "打电话预约看医生",
        "where": "🏥 打给社区诊所",
        "story": "你这两天嗓子疼、有点发烧，想约这周看医生，但诊所说本周很满。",
        "mission": "说清症状、争取尽早的号，并问清要带什么。", "difficulty": 2,
        "points": [
            "你嗓子疼、有点发烧，已经两天了",
            "想约这周看医生，越早越好",
            "问需不需要提前做什么、要带医保卡吗",
        ],
        "imagePrompt": f"a person at home holding a phone to their ear, a wall calendar and a box of "
                       f"medicine and a thermometer on the table, soft daylight, making a clinic appointment, {STYLE}",
    },
    {
        "slug": "ask-for-raise", "kind": "task", "title": "跟老板申请加薪",
        "where": "💼 一对一会议室",
        "story": "你过去一年扛下了好几个项目，但工资两年没动。你约了老板单独聊。",
        "mission": "摆出贡献、提出具体数字、应对'再考虑考虑'。", "difficulty": 3,
        "points": [
            "过去一年你独立扛下 3 个项目，都按时上线",
            "你的工资已经两年没涨了",
            "希望涨 15%，问是否可行",
            "如果老板说再考虑，争取一个明确的答复时间",
        ],
        "imagePrompt": f"a modern office meeting room, two chairs facing each other across a small table, "
                       f"a laptop and a notepad on the table, professional natural daylight, one-on-one meeting, {STYLE}",
    },
    {
        "slug": "assign-tasks", "kind": "task", "title": "给实习生布置任务",
        "where": "📋 工位 · 周一早会",
        "story": "新来的实习生今天第一天，这周有三件事要交给他做。",
        "mission": "把这周的三件任务交代清楚。", "difficulty": 2,
        "points": [
            "任务一：整理上周的用户反馈做成表格，周三前交",
            "任务二：测试新版登录页，最急，今天就要",
            "任务三：写一篇产品更新的短文，周五前",
            "有问题随时来问你",
        ],
        "imagePrompt": f"an office desk with a whiteboard listing a few tasks, sticky notes, a laptop open to "
                       f"a project board, two coffee cups, collaborative workspace, morning light, {STYLE}",
    },
    {
        "slug": "flight-cancelled", "kind": "task", "title": "航班取消争取改签",
        "where": "🧳 机场服务台 · 深夜",
        "story": "你的航班被取消了，明天一早有重要会议，服务台前还排着长队。",
        "mission": "争取最早的改签，并要求安排食宿。", "difficulty": 3,
        "points": [
            "你的航班被取消了，明早有重要会议不能误",
            "要求改到最早的一班",
            "要求安排今晚的酒店和餐食",
        ],
        "imagePrompt": f"airline service desk at an airport at night, a departures board showing a cancelled "
                       f"flight in the background, a suitcase in the foreground, tired travelers waiting, {STYLE}",
    },
    # ── 日常问答 chat（雅思 P1 / 街访，给提示）──
    {
        "slug": "intro-hometown", "kind": "chat", "title": "介绍你的家乡",
        "where": "🎤 街头采访",
        "story": "一个外国博主在街上随机采访你，想了解中国的城市。",
        "mission": "用英语介绍你的家乡。", "difficulty": 1,
        "points": [
            "在哪个城市/省，大概多大",
            "有什么有名的（美食 / 景点 / 特色）",
            "你最喜欢它哪一点",
        ],
        "imagePrompt": f"a person being interviewed on a lively city street, a microphone with a small logo cube "
                       f"held toward the camera, blurred pedestrians and shops behind, vlog street interview vibe, {STYLE}",
    },
    {
        "slug": "phone-habits", "kind": "chat", "title": "聊聊你怎么用手机",
        "where": "🎤 街头采访",
        "story": "街访话题：现代人离不开手机。轮到你了。",
        "mission": "说说你的手机使用习惯。", "difficulty": 1,
        "points": [
            "你每天大概花多久在手机上",
            "主要用哪些 app",
            "觉得手机让生活更好还是更糟，举个例子",
        ],
        "imagePrompt": f"close-up of hands holding a smartphone showing colorful social media app icons, "
                       f"a cafe table and coffee in the background, casual daily life, {STYLE}",
    },
    # ── 描述长谈 describe（雅思 P2 / vlog，给提纲）──
    {
        "slug": "memorable-trip", "kind": "describe", "title": "讲讲难忘的旅行",
        "where": "🎥 拍 vlog",
        "story": "你在拍一条旅行 vlog，对着镜头跟观众聊。",
        "mission": "讲一次你最难忘的旅行。", "difficulty": 2,
        "points": [
            "去了哪里、什么时候、和谁",
            "做了什么印象最深的事",
            "为什么这次旅行让你难忘",
        ],
        "imagePrompt": f"first-person vlog setup, a smartphone on a small tripod facing outward at a scenic "
                       f"travel viewpoint, mountains and open sky in the background, sunny, {STYLE}",
    },
    {
        "slug": "influential-person", "kind": "describe", "title": "影响你最深的人",
        "where": "🎥 对着镜头",
        "story": "你想录一段，聊聊一个改变了你的人。",
        "mission": "描述一个对你影响很大的人。", "difficulty": 2,
        "points": [
            "这个人是谁、和你什么关系",
            "他/她是个什么样的人",
            "具体怎么影响了你",
        ],
        "imagePrompt": f"a warm cozy room with a framed photo standing on a wooden desk, soft window light, "
                       f"a cup of tea, reflective nostalgic mood, {STYLE}",
    },
    {
        "slug": "meaningful-gift", "kind": "describe", "title": "一件难忘的礼物",
        "where": "🎁 聊聊收到的礼物",
        "story": "朋友问你收到过最有意义的礼物是什么。",
        "mission": "描述一件你收到的、很有意义的礼物。", "difficulty": 2,
        "points": [
            "是什么礼物、谁送的、什么场合",
            "为什么对你特别",
            "你当时是什么感受",
        ],
        "imagePrompt": f"a thoughtfully wrapped gift box opened on a wooden table, ribbon and a handwritten "
                       f"card beside it, warm soft light, {STYLE}",
    },
    # ── 观点表达 opinion（雅思 P3 / 采访，给立场+理由提示）──
    {
        "slug": "remote-work", "kind": "opinion", "title": "你怎么看远程办公",
        "where": "🗣️ 观点采访",
        "story": "采访话题：越来越多公司允许在家办公。",
        "mission": "表态并给出理由。", "difficulty": 3,
        "points": [
            "先表明你支持还是反对",
            "给两个理由（如：省通勤时间 / 容易分心、沟通变难）",
            "举一个你自己或身边的例子",
        ],
        "imagePrompt": f"a tidy home office desk with a laptop showing a video call, coffee, a small plant, "
                       f"natural daylight from a window, remote work setting, {STYLE}",
    },
    {
        "slug": "env-action", "kind": "opinion", "title": "为环保你能做什么",
        "where": "🗣️ 观点采访",
        "story": "采访话题：环保不只是政府的事。",
        "mission": "说说普通人能做什么。", "difficulty": 3,
        "points": [
            "普通人能做的小事（少用一次性、垃圾分类、绿色出行）",
            "你自己已经在做的一件",
            "为什么觉得个人行动有意义",
        ],
        "imagePrompt": f"a reusable cloth shopping bag full of fresh vegetables, a bicycle leaning on a wall, "
                       f"recycling bins nearby, bright eco-friendly daily street scene, {STYLE}",
    },
    # ── 讲解科普 explain（TED / 科普，给死内容）──
    {
        "slug": "spring-festival", "kind": "explain", "title": "讲讲春节为什么回家",
        "where": "🥟 讲给外国朋友",
        "story": "外国朋友很好奇：为什么中国人过年一定要回家？",
        "mission": "把春节回家团聚讲清楚。", "difficulty": 2,
        "points": [
            "春节是什么、大概在什么时候",
            "为什么一定要回家团聚（一年一次的全家团圆）",
            "大家会做什么（年夜饭、红包、拜年）",
        ],
        "imagePrompt": f"a festive Chinese New Year family reunion dinner table full of dishes, red lanterns "
                       f"and decorations in the background, warm celebratory atmosphere, {STYLE}",
    },
]


async def main(dry_run: bool) -> None:
    if dry_run:
        for s in SCENARIOS:
            pts = "\n".join(f"    · {p}" for p in s["points"])
            print(f"[{s['kind']}] {s['title']} · {s['where']}（难度{s['difficulty']}）\n  任务: {s['mission']}\n{pts}\n")
        print(f"共 {len(SCENARIOS)} 个场景")
        return

    await connect_db()
    db = get_db()
    created = updated = 0
    for s in SCENARIOS:
        existing = await db.scenarios.find_one({"slug": s["slug"]})
        if existing:
            await db.scenarios.update_one(
                {"_id": existing["_id"]}, {"$set": {k: s[k] for k in TEXT_FIELDS}}
            )
            updated += 1
            print(f"更新文案: {s['slug']}")
            continue

        print(f"生成中: {s['slug']} …")
        image = await wanx_generate(s["imagePrompt"])
        sid = scenario_id()
        key = scenario_image_key(sid)
        await upload_bytes_async(key, image, "image/jpeg")
        doc = {"_id": sid, "slug": s["slug"], "imageKey": key, "imagePrompt": s["imagePrompt"],
               "status": "active", "createdAt": datetime.now(timezone.utc)}
        doc.update({k: s[k] for k in TEXT_FIELDS})
        await db.scenarios.insert_one(doc)
        created += 1
        print(f"完成: {s['slug']} → {key} ({len(image) // 1024} KB)")

    total = await db.scenarios.count_documents({"status": "active"})
    print(f"新建 {created}，更新 {updated}，题库现有 {total} 个场景")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args().dry_run))
