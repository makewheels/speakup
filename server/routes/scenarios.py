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
)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

logger = logging.getLogger(__name__)


def _maybe_topup(user_id: str) -> None:
    """取题时若"没练过的题"不足阈值，后台静默补一道定制题（基于错题本，失败只记日志）。"""
    async def _run():
        try:
            if await fresh_scenario_count(user_id) >= FRESH_THRESHOLD:
                return
            doc = await generate_custom_scenario(user_id)
            if doc:
                logger.info("topped up custom scenario for %s: %s", user_id, doc["slug"])
        except Exception as e:
            logger.warning("scenario top-up failed for %s: %s", user_id, e)

    asyncio.create_task(_run())


@router.get("/next")
async def get_next(userId: str = Query(...)):
    scenario = await next_scenario(userId)
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
