"""自由说话题库：预生成日常口语话题入库，按用户去重抽题，池子用完自动调 LLM 补一批。

- practiced_free_topic_ids：该用户已说过（mode=free 且有 attempt）的话题 id 集合
- next_free_topic：抽一个没说过的话题；池子空先 generate_free_topics 补题再抽
- generate_free_topics：一次 LLM 调用批量生成 n 个话题（≤20），slug 幂等去重后入库

LLM 出口复用 services/corrector.py 的 _get_client + audited_invoke 模式，
测试里被 conftest._no_real_llm 统一拦住，不会真调外部模型。
"""

import json
import logging
import re
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from db.connection import get_db
from services import corrector
from services.llm_audit import audited_invoke, content_to_text
from utils.id_generator import free_topic_id

logger = logging.getLogger(__name__)

# 池子用完时一次补多少题（单次 LLM 调用生成，别太大）
TOPUP_SIZE = 20
# 单次生成上限：一批一个 prompt，太多会降质/超 max_tokens
MAX_BATCH = 20

GENERATE_SYSTEM_PROMPT = """你是英语口语练习 App 的出题编辑。请生成一批"自由说"话题：
用户围绕话题用英语自由发挥，没有固定任务话术。

要求：
- 每个话题是一个**英文短句**（≤12 词），口语化、日常、具体，让人有话可说。
- 覆盖日常生活：衣食住行、工作学习、兴趣爱好、旅行、天气、周末计划、回忆、观点等。
- 不要重复、不要编号、不要问得太宽泛（避免 "Talk about your life" 这类）。
- 形式：Talk about ... / Describe ... / Tell me about ... / What's your favorite ... 等皆可，
  也可以直接用陈述式话题（如 "Your best trip"）。
- 每个话题配一个简短中文释义（≤12 字）。

只输出严格 JSON 数组，不要 markdown，不要任何其他文字：
[{"text": "Your favorite weekend activity", "zh": "你最喜欢的周末活动"}]"""


def slugify(text: str) -> str:
    """话题幂等键：小写、非字母数字转 -、去首尾 -、截 80 字符。"""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:80] or "topic"


def _parse_topics(raw: str) -> dict:
    """解析 LLM 返回的话题 JSON 数组（兼容字符串项 / {text,zh} 对象项 / markdown 围栏）。"""
    text = content_to_text(raw).replace("```json", "").replace("```", "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("no JSON array found")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("top-level JSON is not an array")
    topics: list[dict] = []
    for item in data:
        if isinstance(item, str):
            topic_text, zh = item.strip(), ""
        elif isinstance(item, dict):
            topic_text = str(item.get("text") or "").strip()
            zh = str(item.get("zh") or item.get("chinese") or "").strip()
        else:
            continue
        if topic_text:
            topics.append({"text": topic_text, "zh": zh})
    return {"topics": topics}


async def generate_free_topics(n: int) -> int:
    """调 LLM 批量生成 n 个话题，slug 幂等去重后 insert。返回实际新增条数。"""
    n = max(1, min(int(n or 0), MAX_BATCH))
    messages = [
        SystemMessage(content=GENERATE_SYSTEM_PROMPT),
        HumanMessage(content=f"请生成 {n} 个话题。只输出 JSON 数组。"),
    ]
    result = await audited_invoke(
        corrector._get_client(),
        messages,
        kind="free_topic_gen",
        parser=_parse_topics,
    )
    if result["error"]:
        logger.error("generate_free_topics failed: %s", result["error"])
        return 0
    topics = (result["parsed"] or {}).get("topics") or []

    # slug 幂等：批内去重 + 与库里已有去重
    seen: set[str] = set()
    fresh: list[dict] = []
    for t in topics:
        slug = slugify(t["text"])
        if slug in seen:
            continue
        seen.add(slug)
        fresh.append({"slug": slug, **t})
    if not fresh:
        return 0
    existing = set(await get_db().freeTopics.distinct("slug", {"slug": {"$in": list(seen)}}))
    to_insert = [
        {
            "_id": free_topic_id(),
            "slug": t["slug"],
            "text": t["text"],
            "zh": t["zh"],
            "status": "active",
            "sourceType": "llm",
            "createdAt": datetime.now(timezone.utc),
        }
        for t in fresh
        if t["slug"] not in existing
    ]
    if to_insert:
        await get_db().freeTopics.insert_many(to_insert)
    logger.info("generate_free_topics requested=%d parsed=%d inserted=%d", n, len(topics), len(to_insert))
    return len(to_insert)


async def practiced_free_topic_ids(user_id: str) -> set[str]:
    """该用户已说过的自由话题：mode=free 且至少有一次 attempt 的 freeTopicId 集合。"""
    ids: set[str] = set()
    cursor = get_db().practiceSessions.find(
        {"userId": user_id, "mode": "free", "attempts.0": {"$exists": True}},
        {"freeTopicId": 1},
    )
    async for doc in cursor:
        if doc.get("freeTopicId"):
            ids.add(doc["freeTopicId"])
    return ids


async def _pick_topic(practiced: set[str]) -> dict | None:
    """从 active 池子里随机挑一个没说过的。"""
    query: dict = {"status": "active"}
    if practiced:
        query["_id"] = {"$nin": sorted(practiced)}
    docs = await get_db().freeTopics.aggregate(
        [{"$match": query}, {"$sample": {"size": 1}}]
    ).to_list(1)
    return docs[0] if docs else None


async def next_free_topic(user_id: str) -> dict | None:
    """抽一个该用户没说过的话题；池子用完先自动补一批再抽。无题且补题失败返回 None。"""
    practiced = await practiced_free_topic_ids(user_id)
    doc = await _pick_topic(practiced)
    if doc is None:
        await generate_free_topics(TOPUP_SIZE)
        doc = await _pick_topic(practiced)
    return doc
