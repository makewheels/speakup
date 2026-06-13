"""场景题库服务：取题（定制题优先）+ 因材施教后台生成定制题。

题目存 scenarios 集合：ownerUserId 为 None 是公共题，为 u_xxx 是只出给该用户的定制题。
场景图存 OSS `scenarios/{scenarioId}/cover.jpg`，库里只存 imageKey，URL 读取时现签。
"""

import hashlib
import json
import re
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from db.connection import get_db
from services.corrector import _get_client
from services.oss_storage import get_url as oss_signed_url, upload_bytes_async
from services.wanx import PHOTO_STYLE, wanx_generate
from utils.id_generator import scenario_id

MAX_PENDING_CUSTOM = 2  # 每个用户最多攒 2 道没练过的定制题，攒够就不再生成


def scenario_image_key(sid: str) -> str:
    return f"scenarios/{sid}/cover.jpg"


async def _practiced_scenario_ids(user_id: str) -> set:
    ids = set()
    async for s in get_db().practiceSessions.find(
        {"userId": user_id, "scenarioId": {"$exists": True}}, {"scenarioId": 1}
    ):
        ids.add(s["scenarioId"])
    return ids


async def next_scenario(user_id: str) -> dict | None:
    """取下一题：自己的未练定制题 > 未练公共题 > 随机公共题。返回带签名图 URL 的场景。"""
    practiced = await _practiced_scenario_ids(user_id)

    custom = await get_db().scenarios.find(
        {"ownerUserId": user_id, "status": "active"}
    ).sort("createdAt", 1).to_list(50)
    fresh_custom = [s for s in custom if s["_id"] not in practiced]
    if fresh_custom:
        chosen = fresh_custom[0]
    else:
        public = await get_db().scenarios.find(
            {"ownerUserId": None, "status": "active"}
        ).to_list(200)
        if not public:
            return None
        fresh = [s for s in public if s["_id"] not in practiced]
        pool = fresh or public
        # 没练过的里按难度从低到高；全练过了就按 _id 哈希轮换
        pool.sort(key=lambda s: (s.get("difficulty", 1), s["_id"]))
        chosen = pool[0] if fresh else pool[
            int(hashlib.md5(f"{user_id}{datetime.now().date()}".encode()).hexdigest(), 16) % len(pool)
        ]

    chosen["imageUrl"] = oss_signed_url(chosen["imageKey"]) if chosen.get("imageKey") else ""
    chosen["isCustom"] = chosen.get("ownerUserId") is not None
    return chosen


GEN_PROMPT = """你是英语口语教练的出题人。学习者有几个总是用不好的英语表达（弱点表达），请设计一个真实生活场景任务，让他在完成任务时**天然必须用到这些表达**。

弱点表达：
{words}

要求：
- 场景要具体、有冲突、有完成压力（像"咖啡店做错单且赶飞机"这种），不能是干巴巴的"请描述"。
- mission 必须逼着他说出（或换说法表达）上面的弱点表达。
- 难度适合中国成年学习者日常口语。

只输出 strict JSON，不要 markdown 围栏：
{{
  "where": "带 emoji 的地点，如：☕️ 咖啡店 · 西雅图",
  "story": "2句以内中文情境描述，交代冲突",
  "mission": "1句中文任务指令，以动词开头",
  "imagePrompt": "English photo description of this scene for an image generator, concrete objects and setting, no people's faces close-up"
}}"""


async def generate_custom_scenario(user_id: str) -> dict | None:
    """因材施教：取错题本里最该复习的弱点表达，反向生成一道定制题（含万相配图）。
    设计为后台任务调用，失败返回 None 不抛出。
    """
    db = get_db()
    practiced = await _practiced_scenario_ids(user_id)
    pending = await db.scenarios.count_documents(
        {"ownerUserId": user_id, "status": "active", "_id": {"$nin": list(practiced)}}
    )
    if pending >= MAX_PENDING_CUSTOM:
        return None

    vocab = await db.vocabulary.find({"userId": user_id}).sort("nextReviewAt", 1).to_list(3)
    if not vocab:
        return None
    words = [v["word"] for v in vocab if v.get("word")]
    if not words:
        return None

    word_lines = "\n".join(f"- {v['word']}（他原来说成：{v.get('original', '?')}）" for v in vocab)
    messages = [
        SystemMessage(content=GEN_PROMPT.format(words=word_lines)),
        HumanMessage(content="出一道题。"),
    ]
    raw = (await _get_client().ainvoke(messages)).content
    raw = re.sub(r"```(json)?", "", raw)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    spec = json.loads(raw)

    image = await wanx_generate(f"{spec['imagePrompt']}, {PHOTO_STYLE}")

    now = datetime.now(timezone.utc)
    sid = scenario_id()
    key = scenario_image_key(sid)
    await upload_bytes_async(key, image, "image/jpeg")

    doc = {
        "_id": sid,
        "slug": f"custom-{user_id}-{int(now.timestamp())}",
        "where": spec["where"],
        "story": spec["story"],
        "mission": spec["mission"],
        "difficulty": 2,
        "imageKey": key,
        "imagePrompt": spec["imagePrompt"],
        "ownerUserId": user_id,
        "targetWords": words,
        "status": "active",
        "createdAt": now,
    }
    await db.scenarios.insert_one(doc)
    return doc
