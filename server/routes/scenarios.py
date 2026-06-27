import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.scenario_service import (
    FRESH_THRESHOLD,
    fresh_scenario_count,
    generate_custom_scenario,
    generate_scenario_for_expression,
    next_scenario,
    topup_public_scenario,
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

logger = logging.getLogger(__name__)


def _maybe_topup(user_id: str) -> None:
    """取题时静默补题：用户定制题（基于错题本）+ 公共池按 yaml 坐标系补缺。两条独立失败只记日志。"""
    async def _run():
        try:
            if await fresh_scenario_count(user_id) < FRESH_THRESHOLD:
                doc = await generate_custom_scenario(user_id)
                if doc:
                    logger.info("topped up custom scenario for %s: %s", user_id, doc["slug"])
        except Exception as e:
            logger.warning("custom scenario top-up failed for %s: %s", user_id, e)

        try:
            doc = await topup_public_scenario()
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
):
    scenario = await next_scenario(userId, exclude=exclude, level=level, purpose=purpose)
    if not scenario:
        raise HTTPException(404, "题库为空，请先运行 scripts/generate_scenarios.py")
    _maybe_topup(userId)
    return {
        "scenarioId": scenario["_id"],
        "kind": scenario.get("kind", "task"),
        "title": scenario.get("title", ""),
        "where": scenario.get("where", ""),
        "story": scenario.get("story", ""),
        "mission": scenario.get("mission", ""),
        "points": scenario.get("points", []),
        "imageUrl": scenario.get("imageUrl", ""),
        "isCustom": scenario.get("isCustom", False),
        "targetWords": scenario.get("targetWords", []),
    }


class PracticeWordRequest(BaseModel):
    userId: str
    expression: str
    original: str = ""


@router.post("/practice-word")
async def practice_word(req: PracticeWordRequest):
    """错题本「练这个词」：针对单个表达即时出一道场景题，返回 scenarioId 供前端建练习。"""
    doc = await generate_scenario_for_expression(req.userId, req.expression, req.original)
    if not doc:
        raise HTTPException(400, "出题失败，请重试")
    return {"scenarioId": doc["_id"]}
