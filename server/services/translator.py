"""复习项中文提示词翻译：把地道表达翻成口语化中文。

复习卡正面展示中文提示词（chinese 字段）。新复习项由 corrector 顺带产出；
历史数据缺 chinese 的走 review-items 的 translate 接口惰性补齐。
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from services import corrector
from services.llm_audit import audited_invoke

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是英语口语学习应用的翻译助手。把用户给出的英文表达翻译成自然、口语化的中文，"
    "保留原表达的语气和意图。只输出中文译文本身，不要解释、不要引号、不要附带英文。"
)


async def translate_to_chinese(text: str, link_to: dict | None = None) -> str:
    """把英文表达翻成中文提示词；失败返回空串（调用方按无提示处理，不阻断复习）。"""
    text = (text or "").strip()
    if not text:
        return ""
    result = await audited_invoke(
        corrector._get_client(),
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=text)],
        kind="review_translate",
        link_to=link_to,
    )
    if result["error"]:
        logger.warning("translate_to_chinese failed: %s", result["error"])
        return ""
    raw = (result["raw"] or "").strip()
    return raw.strip('"“”\n ').strip()
