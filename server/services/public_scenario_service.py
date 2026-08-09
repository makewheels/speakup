"""公共题池：按 yaml 坐标系自动补题。"""

import json
import random
import re
import secrets
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from db.connection import get_db
from services.corrector import _get_client
from services.llm_audit import audited_invoke
from services.scenario_images import maybe_gen_image
from services.scenario_preferences import (
    normalized_level,
    normalized_purpose,
    prioritized_topup_candidates,
)
from services.scenario_videos import maybe_gen_video
from utils.id_generator import scenario_id

TAXONOMY_PATH = Path(__file__).parent.parent / "data" / "scenario_taxonomy.yaml"
GENERATION_LEASE_SECONDS = 10 * 60

PUBLIC_GEN_PROMPT = """你是英语口语教练，给中国成年学习者出题。

请严格按以下坐标出一道场景题（不许改 domain / sub / kind / difficulty）：

域：{domain}
子场景：{sub}
kind：{kind}
难度：{difficulty}/3
提示：{note}

# 三段式：情景 / 任务 / 提示——每段都极简，用户没耐心看说明书

## 绝对底线（违反任何一条 = 整道题报废）

❌ **场景绝不能设在考场 / 课堂 / 语言考试 / 面试官评估你的语言能力 / "考官请你描述..."** —— 必须是真实生活处境（咖啡馆、机场、酒店、家里、街头），用户在练真用得上的英语，不是练考试题。
❌ **不准让对方"考"用户**（"请你介绍...的三个传统"、"分别从 A、B、C 阐述"、"讨论利弊"）—— 这些是面试官口吻，不是朋友聊天。

## 情景（story）
- **一句完整自然的中文**，读起来像正常人在说话，约 30-45 字
- 不要剧本式铺垫（"你想去 X / 刚坐上车 / 一脸理所当然 / 心理活动"）
- 也不要新闻标题式短句（两段不连贯的事实拼接）
- **不准在情景里替用户列他要说什么**（"你需要说明 A、B、C" / "你打算挑三个重点"），那是 mission/points 的事
- 反例 1（太啰嗦）：你想去 2 公里外的夜市，刚坐上车，司机就随口报了个比正常价高三倍的价格，还一脸理所当然地看着你。
- 反例 2（太短像标题）：司机要价 300 卢比，正常只需 100。
- 反例 3（混进任务说明）：护士让你填写登记表并口头确认病情，你需要清晰说明哪里不舒服、持续了多久以及过敏情况。
- 正例：你叫了辆突突车去夜市，司机一开口就要 300 卢比，比正常价贵三倍。

## 任务（mission）
- **一句简短的中文指令，约 8-15 字**，让用户一眼看懂"我现在要做什么"
- 反例（太短，禁欲）：砍价 / 礼貌砍价 / 解释春节
- 反例（太长，IELTS 味）：用轻松的语气跟他解释春节的核心活动，让他明白这不只是放假而是家庭团聚
- 正例：跟司机砍价，至少让他降一半 / 跟外国同事解释清楚春节是怎么过的 / 投诉房间问题并要求换房 / 跟护士说清楚哪里痛多久了

## 提示（points）
- **恰好 2 条**——一条主攻角度，一条备用 fallback
- 每条都是**一句用户可以直接照着说的中文话**，他不用思考、直接翻译成英文就行
- ❌ 不准写行为指引（"假装离开"/"摇头不接受"/"深呼吸"）—— 我们练的是口语，不是表演
- ❌ 不准写抽象语气（"语气坚定但礼貌"/"表达诚意"）—— 那些用户做不到
- ❌ 不准写概念列举（"指出价格不合理"）—— 太抽象，用户还得二次翻译
- ✅ 应该是直接能用的中文台词，比如：
  - 反例（砍价场景的烂提示）：[ "假装走开看对方反应", "用坚定语气还价" ]
  - 正例（砍价场景）：[ "地图上看很近，我直接走过去就行", "我刚才问过别人，正常价就 100" ]

# 其他

- 标题、地点不能用 emoji
- 真实可发生，中国成年学习者真生活会用得到
- imagePrompt 仍然要写
- videoPrompt 也要写，描述 5 秒无声短视频：包含场景核心动作、广角/侧面/背影，不要字幕/文字/水印

只输出 strict JSON，不要 markdown 围栏：
{{
  "title": "中文短标题，6-12 字",
  "where": "地点 · 时间，简短，例如：东南亚夜市路口 · 傍晚",
  "story": "一句完整自然的中文，30-45 字，只交代冲突核心，不写心理活动",
  "mission": "8-15 字简短中文指令，看得出'我现在要做什么'",
  "points": ["一句用户可以直接照着说的中文话", "另一句备用 fallback 中文话"],
  "imagePrompt": "English photo description for an image generator. Image MUST visually show the actual scene/conflict from the story (e.g. collapse → person on the floor with bystanders gathered; bargaining → driver and passenger gesturing; airport coffee mistake → counter with cup). People are encouraged in scene — just avoid sharp close-up faces by using wide shots, side angles, back views, or hands-only framing. No abstract 'empty space implying an incident'. No text/captions in image.",
  "videoPrompt": "English 5-second silent video prompt for the same scene. Show the actual conflict and visible human action with gentle camera motion, wide or side-angle shot, no sharp close-up faces, no text/captions/watermarks."
}}"""


def load_taxonomy() -> dict:
    """从 yaml 加载主题骨架。每次调用都重新读，方便热更新。"""
    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def undercovered_subs(skip_ids: set[str] | None = None) -> list[dict]:
    """返回 actual<target 的坐标列表，按 gap 降序、subId 字典序稳定排序。"""
    skip_ids = skip_ids or set()
    tax = load_taxonomy()
    target_default = tax.get("target_per_sub", 2)

    counts: dict[str, int] = {}
    async for d in get_db().scenarios.aggregate([
        {"$match": {
            "ownerUserId": None,
            "status": "active",
            "category.subId": {"$exists": True},
        }},
        {"$group": {"_id": "$category.subId", "n": {"$sum": 1}}},
    ]):
        counts[d["_id"]] = d["n"]

    out = []
    for domain in tax["domains"]:
        for sub in domain["subs"]:
            sub_id = sub["id"]
            if sub_id in skip_ids:
                continue
            target = sub.get("target", target_default)
            actual = counts.get(sub_id, 0)
            gap = target - actual
            if gap <= 0:
                continue
            out.append({
                "domainName": domain["domain"],
                "domainShort": domain["short"],
                "subId": sub_id,
                "subName": sub["sub"],
                "kind": sub["kind"],
                "difficulty": sub["difficulty"],
                "note": sub.get("note", ""),
                "bonusZh": sub.get("bonus_zh", False),
                "actual": actual,
                "target": target,
                "gap": gap,
            })
    random.shuffle(out)
    out.sort(key=lambda x: -x["gap"])
    return out


def _existing_examples_block(examples: list[dict] | None) -> str:
    if not examples:
        return ""
    rows = []
    for index, item in enumerate(examples[:8], 1):
        rows.append(
            f'{index}. 标题「{item.get("title", "")}」；'
            f'情景「{item.get("story", "")}」；'
            f'任务「{item.get("mission", "")}」'
        )
    return (
        "\n\n# 同坐标已有题（新题不得换词复述）\n"
        + "\n".join(rows)
        + "\n必须在具体地点、角色关系、核心冲突和说话目标中至少改变两项，"
          "同时仍严格属于指定子场景。"
    )


def _scenario_similarity(left: dict, right: dict) -> float:
    def normalized(value: object) -> str:
        return re.sub(r"[^\w\u3400-\u9fff]+", "", str(value or "").lower())

    left_text = normalized(" ".join(str(left.get(k, "")) for k in ("title", "story", "mission")))
    right_text = normalized(" ".join(str(right.get(k, "")) for k in ("title", "story", "mission")))
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def _is_near_duplicate(spec: dict, existing: list[dict]) -> bool:
    title = re.sub(r"\W+", "", str(spec.get("title", "")).lower())
    for item in existing:
        other_title = re.sub(r"\W+", "", str(item.get("title", "")).lower())
        if title and title == other_title:
            return True
        if _scenario_similarity(spec, item) >= 0.78:
            return True
    return False


def _validate_spec(spec: dict) -> None:
    missing = [key for key in ("title", "where", "story", "mission") if not str(spec.get(key, "")).strip()]
    points = spec.get("points")
    if missing:
        raise RuntimeError(f"public scenario missing fields: {', '.join(missing)}")
    if not isinstance(points, list) or len(points) != 2 or not all(str(p).strip() for p in points):
        raise RuntimeError("public scenario must contain exactly two non-empty points")


async def _llm_spec_for_coord(
    coord: dict,
    link_to: dict | None = None,
    existing_examples: list[dict] | None = None,
) -> dict:
    """调 LLM 按坐标编故事，返回解析后的 spec dict（不入库不生图）。"""
    system_prompt = PUBLIC_GEN_PROMPT.format(
        domain=coord["domainName"],
        sub=coord["subName"],
        kind=coord["kind"],
        difficulty=coord["difficulty"],
        note=coord["note"],
    ) + _existing_examples_block(existing_examples)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="出一道。"),
    ]

    def _parse(raw: str) -> dict:
        cleaned = re.sub(r"```(json)?", "", raw)
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        return json.loads(cleaned)

    result = await audited_invoke(
        _get_client(), messages, kind="scenario_gen_public", link_to=link_to, parser=_parse,
    )
    if result["error"] or not result["parsed"]:
        raise RuntimeError(f"public scenario gen failed: {result['error']}")
    spec = result["parsed"]
    _validate_spec(spec)
    return spec


async def _acquire_generation_lease(sub_id: str) -> str | None:
    """给子场景加跨进程租约，避免多个请求同时看到 actual<target 后超发。"""
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(18)
    try:
        doc = await get_db().scenarioGenerationLocks.find_one_and_update(
            {
                "_id": sub_id,
                "$or": [
                    {"expiresAt": {"$lte": now}},
                    {"expiresAt": {"$exists": False}},
                ],
            },
            {"$set": {"token": token, "expiresAt": now + timedelta(seconds=GENERATION_LEASE_SECONDS)}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return None
    return token if doc and doc.get("token") == token else None


async def _release_generation_lease(sub_id: str, token: str) -> None:
    await get_db().scenarioGenerationLocks.delete_one({"_id": sub_id, "token": token})


def _base_doc(coord: dict, spec: dict) -> dict:
    return {
        "category": {"domain": coord["domainShort"], "subId": coord["subId"]},
        "kind": coord["kind"],
        "title": spec.get("title", ""),
        "where": spec.get("where", ""),
        "story": spec.get("story", ""),
        "mission": spec.get("mission", ""),
        "points": spec.get("points", []),
        "difficulty": coord["difficulty"],
        "imagePrompt": spec.get("imagePrompt", ""),
        "videoPrompt": spec.get("videoPrompt") or spec.get("imagePrompt", ""),
    }


async def topup_public_scenario(
    skip_ids: set[str] | None = None,
    dry_run: bool = False,
    level: str | None = None,
    purpose: str | None = None,
) -> dict | None:
    """生成 1 道公共题：选 gap 最大的 sub → LLM 编故事 → Seedream 生图 → 入库。"""
    level = normalized_level(level)
    purpose = normalized_purpose(purpose)
    candidates = await undercovered_subs(skip_ids=skip_ids)
    if not candidates:
        return None
    prioritized = prioritized_topup_candidates(candidates, level, purpose)
    if dry_run:
        coord = prioritized[0]
        sid = scenario_id()
        link = {"scenarioId": sid, "subId": coord["subId"]}
        spec = await _llm_spec_for_coord(coord, link_to=link)
        base = _base_doc(coord, spec)
        return {"_dry_run": True, **base, "subName": coord["subName"]}

    for coord in prioritized:
        token = await _acquire_generation_lease(coord["subId"])
        if not token:
            continue
        try:
            query = {
                "ownerUserId": None,
                "status": "active",
                "category.subId": coord["subId"],
            }
            # 锁内重查：undercovered_subs 的计数在等锁期间可能已过期。
            if await get_db().scenarios.count_documents(query) >= coord["target"]:
                continue
            existing = await get_db().scenarios.find(
                query, {"title": 1, "story": 1, "mission": 1}
            ).sort("createdAt", -1).to_list(8)
            sid = scenario_id()
            link = {"scenarioId": sid, "subId": coord["subId"]}
            spec = await _llm_spec_for_coord(coord, link_to=link, existing_examples=existing)
            if _is_near_duplicate(spec, existing):
                # 仅重试一次，并把被拒绝草稿也放进反例，防止无界重试花钱。
                spec = await _llm_spec_for_coord(
                    coord,
                    link_to=link,
                    existing_examples=[*existing, spec],
                )
            if _is_near_duplicate(spec, existing):
                raise RuntimeError(f"public scenario remains too similar for {coord['subId']}")

            base = _base_doc(coord, spec)
            image = await maybe_gen_image(sid, spec.get("imagePrompt", ""), link)
            video = await maybe_gen_video(sid, base["videoPrompt"], link)
            now = datetime.now(timezone.utc)
            doc = {
                "_id": sid,
                "slug": f"auto-{coord['subId']}-{int(now.timestamp())}",
                "imageKey": image,
                "videoKey": video,
                "videoStatus": "ready" if video else "skipped",
                "ownerUserId": None,
                "status": "active",
                "createdAt": now,
                **base,
            }
            await get_db().scenarios.insert_one(doc)
            return doc
        finally:
            await _release_generation_lease(coord["subId"], token)
    return None
