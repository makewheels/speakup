from fastapi import APIRouter, HTTPException, Query

from services.scenario_service import next_scenario

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@router.get("/next")
async def get_next(userId: str = Query(...)):
    scenario = await next_scenario(userId)
    if not scenario:
        raise HTTPException(404, "题库为空，请先运行 scripts/generate_scenarios.py")
    return {
        "scenarioId": scenario["_id"],
        "kind": scenario.get("kind", "task"),
        "title": scenario.get("title", ""),
        "where": scenario.get("where", ""),
        "story": scenario.get("story", ""),
        "mission": scenario.get("mission", ""),
        "imageUrl": scenario.get("imageUrl", ""),
        "isCustom": scenario.get("isCustom", False),
        "targetWords": scenario.get("targetWords", []),
    }
