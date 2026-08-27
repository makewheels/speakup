import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
from services.interaction_types import normalize_interaction_type, scenario_hints
from services.oss_storage import get_url as oss_signed_url
from services.scenario_service import (
    FRESH_THRESHOLD,
    fresh_scenario_count,
    generate_custom_scenario,
    generate_scenario_for_expression,
    next_scenario,
    topup_public_scenario,
)
from utils.data_source import normalize_source_type
from utils.mongo_ids import id_filter

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

logger = logging.getLogger(__name__)

# 指定题目入口的 slug：小写 kebab-case，区分大小写，不做猜测性改写
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SCENARIO_NOT_AVAILABLE = "场景不存在或不可用"


def _scenario_payload(scenario: dict) -> dict:
    """/next 与按 slug 精确读取共用的场景响应契约。

    interactionType 在出口统一归一化（缺失/未知按 standard），
    前端不在多处重复猜测；standard 缺失 hints 时返回空数组。
    """
    return {
        "scenarioId": scenario["_id"],
        "kind": scenario.get("kind", "task"),
        "title": scenario.get("title", ""),
        "where": scenario.get("where", ""),
        "story": scenario.get("story", ""),
        "mission": scenario.get("mission", ""),
        "points": scenario.get("points", []),
        "imageUrl": scenario.get("imageUrl", ""),
        "videoUrl": scenario.get("videoUrl", ""),
        "isCustom": scenario.get("isCustom", False),
        "preferenceMatch": scenario.get("preferenceMatch", "exact"),
        "targetWords": scenario.get("targetWords", []),
        "difficulty": scenario.get("difficulty"),
        "interactionType": normalize_interaction_type(scenario.get("interactionType")),
        "hints": scenario_hints(scenario),
    }


def _maybe_topup(
    user_id: str,
    level: str | None = None,
    purpose: str | None = None,
    source_type: str = "human",
) -> None:
    """取题时静默补题：用户定制题（基于错题本）+ 公共池按 yaml 坐标系补缺。两条独立失败只记日志。"""
    if source_type == "ai_test":
        return

    async def _run():
        try:
            if await fresh_scenario_count(user_id) < FRESH_THRESHOLD:
                doc = await generate_custom_scenario(user_id)
                if doc:
                    logger.info("topped up custom scenario for %s: %s", user_id, doc["slug"])
        except Exception as e:
            logger.warning("custom scenario top-up failed for %s: %s", user_id, e)

        try:
            doc = await topup_public_scenario(level=level, purpose=purpose)
            if doc:
                logger.info(
                    "topped up public scenario: %s [%s]",
                    doc["slug"], doc["category"]["subId"],
                )
        except Exception as e:
            logger.warning("public scenario top-up failed: %s", e)

    asyncio.create_task(_run())


@router.get("/next")
async def get_next(
    userId: str = Query(...),
    exclude: list[str] = Query(default_factory=list),
    level: str | None = Query(default=None),
    purpose: str | None = Query(default=None),
    token_user_id: str = Depends(current_user_id),
):
    assert_same_user(userId, token_user_id)
    scenario = await next_scenario(userId, exclude=exclude, level=level, purpose=purpose)
    if not scenario:
        raise HTTPException(404, "题库为空，请先运行 scripts/generate_scenarios.py")
    user = await get_db().users.find_one(id_filter(token_user_id), {"sourceType": 1})
    _maybe_topup(
        userId,
        level=level,
        purpose=purpose,
        source_type=normalize_source_type((user or {}).get("sourceType")),
    )
    return _scenario_payload(scenario)


@router.get("/by-slug/{slug}")
async def get_scenario_by_slug(slug: str, token_user_id: str = Depends(current_user_id)):
    """按 slug 精确取题：只返回 active 且当前用户可访问的题。

    身份只取 Bearer token。不存在、已归档、slug 非法、无权访问统一 404，
    不回退随机题，也不暴露其他用户定制题的存在。
    """
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(404, SCENARIO_NOT_AVAILABLE)
    scenario = await get_db().scenarios.find_one({"slug": slug, "status": "active"})
    if not scenario or scenario.get("ownerUserId") not in (None, token_user_id):
        raise HTTPException(404, SCENARIO_NOT_AVAILABLE)
    scenario["isCustom"] = scenario.get("ownerUserId") is not None
    scenario["preferenceMatch"] = "exact"
    scenario["imageUrl"] = oss_signed_url(scenario["imageKey"]) if scenario.get("imageKey") else ""
    scenario["videoUrl"] = oss_signed_url(scenario["videoKey"]) if scenario.get("videoKey") else ""
    return _scenario_payload(scenario)


class PracticeWordRequest(BaseModel):
    userId: str
    expression: str
    original: str = ""


@router.post("/practice-word")
async def practice_word(req: PracticeWordRequest, token_user_id: str = Depends(current_user_id)):
    """错题本「练这个词」：针对单个表达即时出一道场景题，返回 scenarioId 供前端建练习。"""
    assert_same_user(req.userId, token_user_id)
    doc = await generate_scenario_for_expression(req.userId, req.expression, req.original)
    if not doc:
        raise HTTPException(400, "出题失败，请重试")
    return {"scenarioId": doc["_id"]}
