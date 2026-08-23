"""只基于题目生成独立标准答案。

此服务的消息构造函数不接收学习者原话、上一轮反馈或纠正结果，并对场景字段做
显式白名单过滤。这样标准答案的上下文隔离由代码结构保证，而不是依赖提示词自律。
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from services.llm_audit import audited_invoke, content_to_text

logger = logging.getLogger(__name__)


STANDARD_ANSWER_SYSTEM_PROMPT = """你和学习者在独立完成同一道英语口语题。
你只能看到题目，绝不能推测、引用或模仿学习者的回答，也看不到任何纠正或历史反馈。

只根据题目给出母语者会自然说出的完整示范：
- 场景题要完成 mission，并覆盖 points 中的必要信息；
- 自由说话题给出一段自然、具体的示范回答；
- 使用真实日常口语，不写教学说明，不提及学习者；
- 英文最多 3 句。

严格只输出 JSON，不要 markdown：
{"standardAnswer": ""}"""


class StandardAnswerResult(BaseModel):
    standardAnswer: str = ""


def _question_snapshot(scenario: dict | None) -> dict:
    """只保留用户实际看到的题目字段；训练词和任何额外元数据一律丢弃。"""
    if not scenario:
        return {}
    if scenario.get("kind") == "free":
        raw_topic = scenario.get("freeTopic")
        topic = raw_topic.strip() if isinstance(raw_topic, str) else ""
        return {"mode": "free", "topic": topic} if topic else {}

    snapshot: dict[str, Any] = {"mode": "scenario"}
    for key in ("title", "where", "story", "mission"):
        raw_value = scenario.get(key)
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if value:
            snapshot[key] = value
    points = [point.strip() for point in scenario.get("points") or [] if isinstance(point, str) and point.strip()]
    if points:
        snapshot["points"] = points
    return snapshot if len(snapshot) > 1 else {}


def build_standard_answer_messages(scenario: dict | None) -> list:
    """构造只含题目白名单快照的消息；函数签名刻意不接收用户作答。"""
    question = _question_snapshot(scenario)
    user = "题目如下，请独立作答：\n" + json.dumps(question, ensure_ascii=False, sort_keys=True)
    return [SystemMessage(content=STANDARD_ANSWER_SYSTEM_PROMPT), HumanMessage(content=user)]


def _clean_json(raw: Any) -> str:
    text = content_to_text(raw).replace("```json", "").replace("```", "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def parse_standard_answer(raw: Any) -> dict:
    try:
        data = json.loads(_clean_json(raw), strict=False)
        if isinstance(data.get("result"), dict):
            data = data["result"]
        answer = data.get("standardAnswer") or data.get("standard_answer") or ""
        return StandardAnswerResult(standardAnswer=str(answer).strip()).model_dump()
    except Exception:
        return StandardAnswerResult().model_dump()


async def generate_standard_answer(
    scenario: dict | None,
    client: Any,
    *,
    link_to: dict | None = None,
) -> str:
    """标准答案严格只调用一次；不可用时安全降级为空。"""
    if not _question_snapshot(scenario):
        return ""

    messages = build_standard_answer_messages(scenario)
    result = await audited_invoke(
        client,
        messages,
        kind="standard_answer",
        link_to=link_to,
        parser=parse_standard_answer,
    )
    parsed = result.get("parsed") or {}
    answer = str(parsed.get("standardAnswer") or "").strip()
    if not result.get("error") and answer:
        return answer
    logger.warning("independent standard answer unavailable; degrading to empty")
    return ""
