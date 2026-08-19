"""自由说话题库种子：内置 60 个手写日常话题（英文+中文），按 slug 幂等 upsert。

- 默认执行插入（幂等），重复跑不会重复建；打印新增条数。
- 目标库默认 dev（MONGO_URI，即当前 .env）；--prod 用 PROD_SYNC_MONGO_URI（写在 .env，不入库）。
- 可选 --llm-topup N：再调 LLM 生成 N 个话题补到池子（真调外部 LLM，默认不调；测试/CI 不带此参数）。

用法（server/ 目录）：
    # 先塞 dev
    uv run python scripts/seed_free_topics.py
    # dev 想补到约 100 个（真调 LLM）
    uv run python scripts/seed_free_topics.py --llm-topup 40
    # 生产另行执行（需 PROD_SYNC_MONGO_URI）
    uv run python scripts/seed_free_topics.py --prod
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from config import MONGO_URI  # noqa: E402

# (英文话题, 中文释义) —— 日常口语自由说话题，短句、具体、让人有话可说
BUILTIN_TOPICS: list[tuple[str, str]] = [
    ("Your favorite breakfast", "你最喜欢的早餐"),
    ("What you did last weekend", "上周末做了什么"),
    ("Your best friend", "你最好的朋友"),
    ("Your dream vacation", "梦想中的假期"),
    ("A movie you watched recently", "最近看的一部电影"),
    ("Your favorite season", "你最喜欢的季节"),
    ("A dish you can cook", "你会做的一道菜"),
    ("Your morning routine", "你的早晨习惯"),
    ("The weather today", "今天的天气"),
    ("Your favorite app on your phone", "手机里最喜欢的应用"),
    ("A book you enjoyed", "一本你喜欢的书"),
    ("Your hometown", "你的家乡"),
    ("A sport you like", "你喜欢的一项运动"),
    ("Your favorite restaurant", "你最喜欢的餐厅"),
    ("A gift you received", "收到过的一份礼物"),
    ("Your job or major", "你的工作或专业"),
    ("A place you want to visit", "想去的一个地方"),
    ("Your favorite music", "你喜欢的音乐"),
    ("A habit you want to build", "想养成的一个习惯"),
    ("Your last shopping trip", "上一次购物"),
    ("A pet you had or want", "养过或想养的宠物"),
    ("Your favorite holiday", "你最喜欢的节日"),
    ("A skill you want to learn", "想学的一项技能"),
    ("Your ideal weekend", "理想的周末"),
    ("A memorable trip", "一次难忘的旅行"),
    ("Your favorite drink", "你最喜欢的饮料"),
    ("A teacher you remember", "一位你记得的老师"),
    ("Your neighborhood", "你住的街区"),
    ("A goal for this year", "今年的一个目标"),
    ("Your favorite store", "你最喜欢的一家店"),
    ("A childhood memory", "一段童年回忆"),
    ("How you relax after work", "下班后你怎么放松"),
    ("Your favorite piece of clothing", "最喜欢的一件衣服"),
    ("A city you have lived in", "生活过的一座城市"),
    ("Your daily commute", "你的日常通勤"),
    ("A recent purchase", "最近买的一件东西"),
    ("Your favorite TV show", "最喜欢的一部剧"),
    ("A family tradition", "家里的一个传统"),
    ("Your dream home", "梦想中的家"),
    ("A park you like", "你喜欢的一个公园"),
    ("Your favorite way to exercise", "最喜欢的锻炼方式"),
    ("A stranger who helped you", "帮助过你的陌生人"),
    ("Your phone habits", "你的用手机习惯"),
    ("A concert or event you attended", "参加过的一场演出或活动"),
    ("Your favorite snack", "你最喜欢的零食"),
    ("A language you want to learn", "想学的一门语言"),
    ("Your bedtime routine", "你的睡前习惯"),
    ("A photo you love", "一张你喜欢的照片"),
    ("Your favorite cafe", "你最喜欢的一家咖啡馆"),
    ("A mistake you learned from", "从错误中学到的东西"),
    ("Your first job", "你的第一份工作"),
    ("A gift you gave someone", "送给别人的一份礼物"),
    ("Your favorite thing about your city", "所在城市你最喜欢的一点"),
    ("A museum or exhibition you visited", "参观过的一次博物馆或展览"),
    ("Your ideal birthday", "理想的生日"),
    ("A new food you tried", "尝试过的一种新食物"),
    ("Your study habits", "你的学习习惯"),
    ("A neighbor you know", "你认识的一位邻居"),
    ("A happy memory from school", "上学时的一段美好回忆"),
    ("What makes you happy", "什么让你开心"),
]


def slugify(text: str) -> str:
    # 与 services/free_practice.py 保持一致；避免脚本依赖服务层导入链
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:80] or "topic"


async def main(prod: bool, llm_topup: int) -> None:
    uri = os.getenv("PROD_SYNC_MONGO_URI", "") if prod else MONGO_URI
    if prod and not uri:
        print("❌ --prod 需要 PROD_SYNC_MONGO_URI（写在 .env，不入库）。")
        return

    # 直连目标库；同时把它挂到 db.connection，供 --llm-topup 的 generate_free_topics 用
    import db.connection as connection
    from datetime import datetime, timezone
    from utils.id_generator import free_topic_id

    connection.client = AsyncIOMotorClient(uri, tz_aware=True)
    connection.db = connection.client.get_default_database()
    db = connection.db
    target = db.client.address
    print(f"目标库：{'prod' if prod else 'dev'} ({target[0]}:{target[1]}/{db.name})")

    existing = set(await db.freeTopics.distinct("slug"))
    docs = []
    for text, zh in BUILTIN_TOPICS:
        slug = slugify(text)
        if slug in existing:
            continue
        docs.append({
            "_id": free_topic_id(),
            "slug": slug,
            "text": text,
            "zh": zh,
            "status": "active",
            "sourceType": "seed",
            "createdAt": datetime.now(timezone.utc),
        })
    if docs:
        await db.freeTopics.insert_many(docs)
    print(f"内置话题 {len(BUILTIN_TOPICS)} 个：新增 {len(docs)}，跳过已存在 {len(BUILTIN_TOPICS) - len(docs)}。")

    if llm_topup > 0:
        from services.free_practice import generate_free_topics

        inserted = await generate_free_topics(llm_topup)
        print(f"LLM 补题：请求 {llm_topup} 个，实际新增 {inserted} 个。")

    total = await db.freeTopics.count_documents({"status": "active"})
    print(f"当前 active 话题池共 {total} 个。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prod", action="store_true", help="写生产库（默认写 dev 库）")
    parser.add_argument("--llm-topup", type=int, default=0, help="额外调 LLM 生成 N 个话题（默认 0=不调外部 LLM）")
    args = parser.parse_args()
    asyncio.run(main(args.prod, args.llm_topup))
