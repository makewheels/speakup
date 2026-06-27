"""场景题库服务：取题（定制题优先）+ 因材施教后台生成定制题 + 公共池按 yaml 坐标系自动补题。

题目存 scenarios 集合：ownerUserId 为 None 是公共题，为 u_xxx 是只出给该用户的定制题。
场景图存 OSS `scenarios/{scenarioId}/cover.jpg`，库里只存 imageKey，URL 读取时现签。

公共池增长靠 `data/scenario_taxonomy.yaml`：每个 (domain × sub) 是一个坐标，目标 N 道；
取题时用户触发后台 topup → 找 actual<target 的坐标 → LLM 按坐标编故事 → 入库。全部
达 target 后短路停止花钱；要扩容只改 yaml。
"""

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

from config import IMAGE_ENABLED
from db.connection import get_db
from services.corrector import _get_client
from services.llm_audit import audited_invoke
from services.oss_storage import get_url as oss_signed_url, upload_bytes_async
from services.wanx import PHOTO_STYLE, wanx_generate
from utils.id_generator import scenario_id

MAX_PENDING_CUSTOM = 2  # 每个用户最多攒 2 道没练过的定制题，攒够就不再生成
FRESH_THRESHOLD = 3     # 没练过的题少于这个数时，取题会后台补一道定制题

TAXONOMY_PATH = Path(__file__).parent.parent / "data" / "scenario_taxonomy.yaml"

LEVEL_DIFFICULTIES = {
    "beginner": {1},
    "daily": {1, 2},
    "advanced": {2, 3},
    "challenge": {3},
}

PURPOSE_FILTERS = {
    # 低压开口：寒暄和轻任务为主，避开硬核解释/观点题。
    "openup": {
        "domains": {"social", "hobby", "food", "travel", "lodging", "shopping"},
        "kinds": {"chat", "task"},
    },
    "travel": {
        "domains": {"travel", "lodging", "food", "shopping", "health", "bank", "telecom", "emergency"},
    },
    "work": {
        "domains": {"work", "job", "biz"},
    },
    "expression": {
        "kinds": {"describe", "opinion", "explain"},
    },
}


def _normalized_level(level: str | None) -> str | None:
    return level if level in LEVEL_DIFFICULTIES else None


def _normalized_purpose(purpose: str | None) -> str | None:
    return purpose if purpose in {*PURPOSE_FILTERS.keys(), "review"} else None


def _relaxed_difficulties(level: str | None) -> set[int] | None:
    if not level:
        return None
    values = LEVEL_DIFFICULTIES[level]
    lo = max(1, min(values) - 1)
    hi = min(3, max(values) + 1)
    return set(range(lo, hi + 1))


def _scenario_domain(scenario: dict) -> str:
    return (scenario.get("category") or {}).get("domain", "")


def _matches_purpose(scenario: dict, purpose: str | None) -> bool:
    if not purpose or purpose == "review":
        return True
    f = PURPOSE_FILTERS[purpose]
    domain_ok = "domains" not in f or _scenario_domain(scenario) in f["domains"]
    kind_ok = "kinds" not in f or scenario.get("kind", "task") in f["kinds"]
    return domain_ok and kind_ok


def _matches_difficulty(scenario: dict, difficulties: set[int] | None) -> bool:
    if not difficulties:
        return True
    return scenario.get("difficulty") in difficulties


def _filtered(pool: list[dict], difficulties: set[int] | None, purpose: str | None) -> list[dict]:
    return [
        s for s in pool
        if _matches_difficulty(s, difficulties) and _matches_purpose(s, purpose)
    ]


def _pick_public(
    public: list[dict],
    practiced: set[str],
    skipped: set[str],
    level: str | None,
    purpose: str | None,
) -> dict:
    blocked = practiced | skipped
    layers = [
        [s for s in public if s["_id"] not in blocked],
        [s for s in public if s["_id"] not in practiced],
        [s for s in public if s["_id"] not in skipped],
        public,
    ]

    if level or purpose:
        strict = LEVEL_DIFFICULTIES.get(level)
        relaxed = _relaxed_difficulties(level)
        filter_steps = [
            (strict, purpose),
            (relaxed, purpose),
            (strict, None),
        ]
        for base in layers:
            for difficulties, p in filter_steps:
                pool = _filtered(base, difficulties, p)
                if pool:
                    return random.choice(pool)

    for base in layers:
        if base:
            return random.choice(base)
    return random.choice(public)


def scenario_image_key(sid: str) -> str:
    return f"scenarios/{sid}/cover.jpg"


async def _maybe_gen_image(sid: str, image_prompt: str, link: dict | None = None) -> str:
    """生成配图存 OSS，返回 imageKey。IMAGE_ENABLED=false 时跳过生成、返回空串（前端按无图渲染）。"""
    if not IMAGE_ENABLED or not image_prompt:
        return ""
    image = await wanx_generate(f"{image_prompt}, {PHOTO_STYLE}", link_to=link)
    key = scenario_image_key(sid)
    await upload_bytes_async(key, image, "image/jpeg")
    return key


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
    level = _normalized_level(level)
    purpose = _normalized_purpose(purpose)
    practiced = await _practiced_scenario_ids(user_id)
    skipped = set(exclude or [])
    blocked = practiced | skipped

    custom = await get_db().scenarios.find(
        {"ownerUserId": user_id, "status": "active"}
    ).sort("createdAt", 1).to_list(50)
    fresh_custom = [s for s in custom if s["_id"] not in blocked]
    if fresh_custom and (purpose in {None, "review"}):
        chosen = fresh_custom[0]
    else:
        public = await get_db().scenarios.find(
            {"ownerUserId": None, "status": "active"}
        ).to_list(200)
        if not public:
            return fresh_custom[0] if fresh_custom else None
        chosen = _pick_public(public, practiced, skipped, level, purpose)

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
  "title": "中文短标题，如：咖啡店给错咖啡",
  "where": "地点，纯文字不要 emoji，如：咖啡店 · 西雅图",
  "story": "2句以内中文情境描述，交代冲突",
  "mission": "1句中文任务指令，以动词开头",
  "imagePrompt": "English photo description of this scene for an image generator, concrete objects and setting, no people's faces close-up"
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
    link = {"scenarioId": sid, "userId": user_id}

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
    key = await _maybe_gen_image(sid, spec["imagePrompt"], link)

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
        "ownerUserId": user_id,
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

    items = await db.reviewItems.find({"userId": user_id}).sort("nextReviewAt", 1).to_list(3)
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


# ---------- 公共题池：按 yaml 坐标系自动补题 ----------

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

只输出 strict JSON，不要 markdown 围栏：
{{
  "title": "中文短标题，6-12 字",
  "where": "地点 · 时间，简短，例如：东南亚夜市路口 · 傍晚",
  "story": "一句完整自然的中文，30-45 字，只交代冲突核心，不写心理活动",
  "mission": "8-15 字简短中文指令，看得出'我现在要做什么'",
  "points": ["一句用户可以直接照着说的中文话", "另一句备用 fallback 中文话"],
  "imagePrompt": "English photo description for an image generator. Image MUST visually show the actual scene/conflict from the story (e.g. collapse → person on the floor with bystanders gathered; bargaining → driver and passenger gesturing; airport coffee mistake → counter with cup). People are encouraged in scene — just avoid sharp close-up faces by using wide shots, side angles, back views, or hands-only framing. No abstract 'empty space implying an incident'. No text/captions in image."
}}"""


def load_taxonomy() -> dict:
    """从 yaml 加载主题骨架。每次调用都重新读，方便热更新。"""
    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def undercovered_subs(skip_ids: set[str] | None = None) -> list[dict]:
    """返回 actual<target 的坐标列表，按 gap 降序、subId 字典序稳定排序。

    skip_ids: 不参与排序的 subId 集合（脚本批量跑时用来避免同 sub 选两次）。
    """
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
    # 同 gap 内 shuffle，避免空池子时所有人都先生成 bank.* / biz.*（字母序前缀）；
    # 不同 gap 之间仍按 gap 大的优先（缺得越多越先补）。
    random.shuffle(out)
    out.sort(key=lambda x: -x["gap"])
    return out


async def _llm_spec_for_coord(coord: dict, link_to: dict | None = None) -> dict:
    """调 LLM 按坐标编故事，返回解析后的 spec dict（不入库不生图）。
    link_to 用于 audit 表挂 scenarioId。
    """
    messages = [
        SystemMessage(content=PUBLIC_GEN_PROMPT.format(
            domain=coord["domainName"],
            sub=coord["subName"],
            kind=coord["kind"],
            difficulty=coord["difficulty"],
            note=coord["note"],
        )),
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
    return result["parsed"]


async def topup_public_scenario(
    skip_ids: set[str] | None = None,
    dry_run: bool = False,
) -> dict | None:
    """生成 1 道公共题：选 gap 最大的 sub → LLM 编故事 → Seedream 生图 → 入库。

    dry_run=True 只跑 LLM 拿文案，不调生图、不入库；用来验证 prompt 质量。
    全部 sub 达 target 时返回 None（系统短路停止花钱）。
    """
    candidates = await undercovered_subs(skip_ids=skip_ids)
    if not candidates:
        return None
    coord = candidates[0]
    sid = scenario_id()  # 提前生成，让 audit + image 都挂同一个 scenarioId
    link = {"scenarioId": sid, "subId": coord["subId"]}
    spec = await _llm_spec_for_coord(coord, link_to=link)

    base = {
        "category": {"domain": coord["domainShort"], "subId": coord["subId"]},
        "kind": coord["kind"],
        "title": spec.get("title", ""),
        "where": spec.get("where", ""),
        "story": spec.get("story", ""),
        "mission": spec.get("mission", ""),
        "points": spec.get("points", []),
        "difficulty": coord["difficulty"],
        "imagePrompt": spec.get("imagePrompt", ""),
    }
    if dry_run:
        return {"_dry_run": True, **base, "subName": coord["subName"]}

    image = await _maybe_gen_image(sid, spec.get("imagePrompt", ""), link)
    now = datetime.now(timezone.utc)

    doc = {
        "_id": sid,
        "slug": f"auto-{coord['subId']}-{int(now.timestamp())}",
        "imageKey": image,
        "ownerUserId": None,
        "status": "active",
        "createdAt": now,
        **base,
    }
    await get_db().scenarios.insert_one(doc)
    return doc
