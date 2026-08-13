import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_db
from services.auth_tokens import assert_same_user, current_user_id
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
    }


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
