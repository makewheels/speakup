"""场景题库服务：取题（定制题优先）+ 因材施教后台生成定制题 + 公共池按 yaml 坐标系自动补题。

题目存 scenarios 集合：ownerUserId 为 None 是公共题，为 u_xxx 是只出给该用户的定制题。
场景图存 OSS `scenarios/{scenarioId}/cover.jpg`，库里只存 imageKey，URL 读取时现签。
场景视频同理存 `scenarios/{scenarioId}/cover.mp4`，前端视频优先、图片兜底。

公共池增长靠 `data/scenario_taxonomy.yaml`：每个 (domain × sub) 是一个坐标，目标 N 道；
取题时用户触发后台 topup → 找 actual<target 的坐标 → LLM 按坐标编故事 → 入库。全部
达 target 后短路停止花钱；要扩容只改 yaml。
"""

import json
import re
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from db.connection import get_db
from services import public_scenario_service
from services.corrector import _get_client
from services.llm_audit import audited_invoke
from services.oss_storage import get_url as oss_signed_url
from services.scenario_images import maybe_gen_image
from services.scenario_preferences import normalized_level, normalized_purpose, pick_public
from services.scenario_videos import maybe_gen_video
from services.wanx import wanx_generate
from utils.data_source import normalize_source_type
from utils.id_generator import scenario_id

MAX_PENDING_CUSTOM = 2  # 每个用户最多攒 2 道没练过的定制题，攒够就不再生成
FRESH_THRESHOLD = 3     # 没练过的题少于这个数时，取题会后台补一道定制题

load_taxonomy = public_scenario_service.load_taxonomy
_llm_spec_for_coord = public_scenario_service._llm_spec_for_coord


async def undercovered_subs(skip_ids: set[str] | None = None) -> list[dict]:
    """兼容旧 patch 点，实际实现委托给 public_scenario_service。"""
    original_load = public_scenario_service.load_taxonomy
    original_get_db = public_scenario_service.get_db
    try:
        public_scenario_service.load_taxonomy = load_taxonomy
        public_scenario_service.get_db = get_db
        return await public_scenario_service.undercovered_subs(skip_ids)
    finally:
        public_scenario_service.load_taxonomy = original_load
        public_scenario_service.get_db = original_get_db


async def topup_public_scenario(
    skip_ids: set[str] | None = None,
    dry_run: bool = False,
    level: str | None = None,
    purpose: str | None = None,
) -> dict | None:
    """兼容旧 patch 点，实际实现委托给 public_scenario_service。"""
    original_load = public_scenario_service.load_taxonomy
    original_get_db = public_scenario_service.get_db
    original_client = public_scenario_service._get_client
    original_llm_spec = public_scenario_service._llm_spec_for_coord
    try:
        public_scenario_service.load_taxonomy = load_taxonomy
        public_scenario_service.get_db = get_db
        public_scenario_service._get_client = _get_client
        public_scenario_service._llm_spec_for_coord = _llm_spec_for_coord
        return await public_scenario_service.topup_public_scenario(
            skip_ids=skip_ids,
            dry_run=dry_run,
            level=level,
            purpose=purpose,
        )
    finally:
        public_scenario_service.load_taxonomy = original_load
        public_scenario_service.get_db = original_get_db
        public_scenario_service._get_client = original_client
        public_scenario_service._llm_spec_for_coord = original_llm_spec


async def _practiced_scenario_ids(user_id: str) -> set:
    """已经"开口评估过至少 1 次"的 scenarioId（attempts 非空）。
    只看了图没说话的不算练过——下次还会再被推出来。
    """
    ids = set()
    async for s in get_db().practiceSessions.find(
        {
            "userId": user_id,
            "scenarioId": {"$exists": True},
            "attempts.0": {"$exists": True},
        },
        {"scenarioId": 1},
    ):
        ids.add(s["scenarioId"])
    return ids


async def next_scenario(
    user_id: str,
    exclude: list[str] | None = None,
    level: str | None = None,
    purpose: str | None = None,
) -> dict | None:
    """取下一题：自己的未练定制题 > 未练公共题 > 随机公共题。返回带签名图 URL 的场景。

    exclude：本会话内已经"看过但跳过"的 scenarioId，强制排除（用于首页 ↻ 换题）。
    """
    level = normalized_level(level)
    purpose = normalized_purpose(purpose)
    practiced = await _practiced_scenario_ids(user_id)
    skipped = set(exclude or [])
    blocked = practiced | skipped

    custom = await get_db().scenarios.find(
        {"ownerUserId": user_id, "status": "active"}
    ).sort("createdAt", 1).to_list(50)
    fresh_custom = [s for s in custom if s["_id"] not in blocked]
    if fresh_custom and (purpose in {None, "review"}):
        chosen = fresh_custom[0]
        preference_match = "custom"
    else:
        public = await get_db().scenarios.find(
            {"ownerUserId": None, "status": "active"}
        ).to_list(200)
        if not public:
            if not fresh_custom:
                return None
            chosen = fresh_custom[0]
            preference_match = "custom"
        else:
            chosen, preference_match = pick_public(public, practiced, skipped, level, purpose)

    chosen["imageUrl"] = oss_signed_url(chosen["imageKey"]) if chosen.get("imageKey") else ""
    chosen["videoUrl"] = oss_signed_url(chosen["videoKey"]) if chosen.get("videoKey") else ""
    chosen["isCustom"] = chosen.get("ownerUserId") is not None
    chosen["preferenceMatch"] = preference_match
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
  "title": "中文短标题，如：咖啡店给错咖啡",
  "where": "地点，纯文字不要 emoji，如：咖啡店 · 西雅图",
  "story": "2句以内中文情境描述，交代冲突",
  "mission": "1句中文任务指令，以动词开头",
  "imagePrompt": "English photo description of this scene for an image generator, concrete objects and setting, no people's faces close-up",
  "videoPrompt": "English short video prompt for the same scene, include visible action and camera motion, no text"
}}"""


async def _build_scenario_doc(user_id: str, specs: list[dict]) -> dict:
    """specs: [{"expression": str, "original": str}]。调 LLM 反向出题 + Seedream 配图，落库，返回 doc。"""
    word_lines = "\n".join(
        f"- {s['expression']}（他原来说成：{s.get('original') or '?'}）" for s in specs
    )
    words = [s["expression"] for s in specs]
    messages = [
        SystemMessage(content=GEN_PROMPT.format(words=word_lines)),
        HumanMessage(content="出一道题。"),
    ]
    sid = scenario_id()  # 提前生成 sid 让 audit + image 都能挂上
    user = await get_db().users.find_one({"_id": user_id}, {"sourceType": 1})
    source_type = normalize_source_type((user or {}).get("sourceType"))
    link = {"scenarioId": sid, "userId": user_id, "sourceType": source_type}

    def _parse(raw: str) -> dict:
        cleaned = re.sub(r"```(json)?", "", raw)
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        return json.loads(cleaned)

    result = await audited_invoke(
        _get_client(), messages, kind="scenario_gen_custom", link_to=link, parser=_parse,
    )
    if result["error"] or not result["parsed"]:
        raise RuntimeError(f"custom scenario gen failed: {result['error']}")
    spec = result["parsed"]

    now = datetime.now(timezone.utc)
    key = await maybe_gen_image(sid, spec["imagePrompt"], link, wanx_generate)
    video_prompt = spec.get("videoPrompt") or spec.get("imagePrompt", "")
    video_key = await maybe_gen_video(sid, video_prompt, link)

    doc = {
        "_id": sid,
        "slug": f"custom-{user_id}-{int(now.timestamp())}",
        "kind": "task",  # 因材施教的定制题都是"逼你用上弱点表达"的办事场景
        "title": spec.get("title", "为你定制"),
        "where": spec["where"],
        "story": spec["story"],
        "mission": spec["mission"],
        "difficulty": 2,
        "imageKey": key,
        "imagePrompt": spec["imagePrompt"],
        "videoKey": video_key,
        "videoPrompt": video_prompt,
        "videoStatus": "ready" if video_key else "skipped",
        "ownerUserId": user_id,
        "sourceType": source_type,
        "targetWords": words,
        "status": "active",
        "createdAt": now,
    }
    await get_db().scenarios.insert_one(doc)
    return doc


async def generate_custom_scenario(user_id: str) -> dict | None:
    """因材施教：取错题本里最该复习的弱点表达，反向生成一道定制题（含 Seedream 配图）。
    设计为后台任务调用，失败返回 None 不抛出。攒够 pending 就跳过。
    """
    db = get_db()
    practiced = await _practiced_scenario_ids(user_id)
    pending = await db.scenarios.count_documents(
        {"ownerUserId": user_id, "status": "active", "_id": {"$nin": list(practiced)}}
    )
    if pending >= MAX_PENDING_CUSTOM:
        return None

    items = await db.reviewItems.find(
        {"userId": user_id, "status": {"$ne": "retired"}}
    ).sort("nextReviewAt", 1).to_list(3)
    specs = [
        {"expression": v["expression"], "original": v.get("original", "")}
        for v in items if v.get("expression")
    ]
    if not specs:
        return None
    return await _build_scenario_doc(user_id, specs)


async def generate_scenario_for_expression(
    user_id: str, expression: str, original: str = ""
) -> dict | None:
    """针对单个弱点表达即时出题（错题本「练这个词」）。同步调用，不受 pending 上限限制。"""
    expression = (expression or "").strip()
    if not expression:
        return None
    return await _build_scenario_doc(user_id, [{"expression": expression, "original": original}])


async def fresh_scenario_count(user_id: str) -> int:
    """用户还没练过的题数（公共 active + 自己的定制 active），用于判断要不要补题。"""
    practiced = await _practiced_scenario_ids(user_id)
    return await get_db().scenarios.count_documents({
        "status": "active",
        "_id": {"$nin": list(practiced)},
        "$or": [{"ownerUserId": None}, {"ownerUserId": user_id}],
    })
