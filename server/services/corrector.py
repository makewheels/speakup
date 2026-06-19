import re
import time
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import CHAT_MODEL, DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL
from services.llm_audit import (
    _safe_insert as audit_safe_insert,
    audited_invoke,
    estimate_text_cost,
)

_API_TIMEOUT = 60.0
_client: ChatOpenAI | None = None

MAX_ROUNDS = 2


class GapItem(BaseModel):
    title: str = ""
    original: str = ""
    better: str = ""
    example: str = ""
    why: str = ""
    category: Literal["grammar", "naturalness", "vocabulary", "register"] = "vocabulary"
    saveToReview: bool = False


class ProgressInfo(BaseModel):
    verdict: Literal["passed", "improved", "stuck"] = "improved"
    fixed: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    comment: str = ""


class CorrectResult(BaseModel):
    summary: str = ""
    nativeVersion: str = ""
    score: float | None = None  # 雅思口语级别 0~9，0.5 进制
    gaps: list[GapItem] = Field(default_factory=list)
    progress: ProgressInfo | None = None


def _get_client() -> ChatOpenAI:
    global _client
    if _client is None:
        _client = ChatOpenAI(
            openai_api_base=f"{DASHSCOPE_BASE_URL}/compatible-mode/v1",
            openai_api_key=DASHSCOPE_API_KEY,
            model=CHAT_MODEL,
            temperature=0.3,
            max_tokens=2000,
            model_kwargs={"extra_body": {"enable_thinking": False}},
            timeout=_API_TIMEOUT,
        )
    return _client


SYSTEM_PROMPT = """你是英语教练，帮助一个中国成年学习者练习真实生活场景下的英语口语。

设定：学习者拿到一个场景题（地点、情境、需要用英语完成的任务）。你拿到这个场景，以及他实际说出来的话。

你的工作：找出他说的内容跟"native speaker 在同样场景下完成同样任务"之间的差距。
真实口语英语——口语化、有生气、贴合场合；不是教科书式的、不是学术式的。

要做的事：
1. 把他的话当成场景里的真实回应来判断：他完成任务的方式是不是 native 会用的？
2. 找出 gaps —— native 不会用的措辞、跟场合不对的语体、缺失的表达动作（比如软化请求、表明紧迫）。按影响力排序。
3. 每个 gap 解释 native 为什么这么说。
4. 最多列 2 个 gaps —— 只选影响最大的。可以一个都没有。偏向小而精的改动（通常 1-3 个词），不要凑数。

不要做的事：
- 不要改他想表达的核心意思——只改"怎么表达"。
- 不要推荐生僻词或学术词。
- 不要写场面话或鼓励（"做得真棒！"）。
- 含义清晰的小笔误或语音识别杂音不要纠正。

硬性约束：
- `nativeVersion` 是对学习者原话的直接改写——保留他的内容和意图，只改"怎么说"。不要凭空换成完全不同的答案或加他没想表达的内容。
- `nativeVersion` 最多 3 句——紧凑，是 native 真会大声说出来的话。
- 每个 gap 的 `better` 必须**逐字出现**在 `nativeVersion` 里，这样 gaps 和 native version 严格对得上。

打分（按 IELTS 口语 band）：
- `score`：0-9 之间的数，以 0.5 为步进（比如 5.0、6.5、7.0）。以 IELTS 考官口吻评这一段：流利度+连贯、词汇、语法宽度+准确度、任务完成度。要实事求是——典型中国学习者在 5.0-6.5；7.5+ 留给真正接近 native 的自然英语。短的、破的、跑题的，分要打低。

反馈语言（严格规定）：
- `summary`: 必须中文，严格不超过 25 字，一句话。
- `nativeVersion` / gap `original` / `better` / `example`: 必须英文。
- gap `why`: 必须中文（可嵌英文词）。对照式解释——既点明"原说法哪里不好"（生硬/语法错/语体不对/不自然），又说"地道说法为什么更好"。例如："but 太生硬，actually 更自然地引出纠正" / "had had 是时态错误，应该用一般过去时"。一句话，尽量简短（≤40 字），不要长篇、不要举多例。

输出：严格 JSON，无 markdown 围栏，无任何解说。

{
  "summary": "一句话（中文，最多 25 字）：最关键的一个差距",
  "nativeVersion": "学习者原话的直接改写——native、自然，最多 3 句；每个 gap 的 better 必须逐字出现",
  "score": 6.5,
  "gaps": [
    {
      "title": "2-5 字中文标签，例如：请求语气、过去时态、催促方式",
      "original": "他说的话（原文或近似改写，英文）",
      "better": "一个 native 替换说法（最好 1-3 个词的小修），仅英文，不要 slash 选项——必须逐字出现在 nativeVersion 里",
      "example": "一句 native 在该场景里真会说的话，自然用上 better",
      "why": "中文对照解释（≤40 字）：原说法哪里不好 + 地道说法为什么更好",
      "category": "grammar",
      "saveToReview": true
    }
  ]
}

`category` 必须是：grammar / naturalness / vocabulary / register 之一。
`saveToReview`：如果记住这个表达能明显提升日常流利度，true；只是一次性的风格差异，false。"""

RETRY_PROMPT = """

这是第 {round} 轮——同一道题的重说尝试。他上一轮说的话和你上次指出的 gaps：
上一轮原话："{prev_text}"
上次指出的 gaps（original -> better）：{prev_gaps}

把这一轮和上一轮对比。在 JSON 输出里**必须额外加一个 progress 字段**：

"progress": {{
  "verdict": "passed | improved | stuck",
  "fixed": ["他这一轮成功用上的某个建议表达——每条是一个独立短句，不要箭头"],
  "remaining": ["仍然没用上的某个建议表达——每条一个独立短句"],
  "comment": "一句中文点评，不超过 20 字"
}}

verdict 规则：
- "passed"：没什么大 gap 了——现在听起来已经像 native 在处理这个任务。要慷慨：小风格瑕疵不阻挡 pass。
- "improved"：明显进步但仍有真 gap。
- "stuck"：同样的问题仍在。

在 "gaps" 里，只列**新出现的或仍未修好的**。聚焦在剩下的问题上，不要重复他已经修好的。"""


_EMPTY = {
    "summary": "",
    "nativeVersion": "",
    "score": None,
    "gaps": [],
    "progress": None,
}


def _scenario_block(scenario: dict | None) -> str:
    if not scenario:
        return ""
    target = ""
    if scenario.get("targetWords"):
        target = f"\nExpressions this learner is training (check if they used them): {', '.join(scenario['targetWords'])}"
    points = ""
    if scenario.get("points"):
        bullets = "\n".join(f"  · {p}" for p in scenario["points"])
        points = f"\n- 应说到的内容（检查是否表达到位）:\n{bullets}"
    return (
        f"SCENARIO:\n"
        f"- 地点: {scenario.get('where', '')}\n"
        f"- 情境: {scenario.get('story', '')}\n"
        f"- 任务: {scenario.get('mission', '')}{points}{target}\n\n"
    )


def _build_messages(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
) -> list:
    system = SYSTEM_PROMPT
    if prev_attempt and round > 1:
        gaps_brief = "; ".join(
            f'"{g.get("original", "")}" -> "{g.get("better", "")}"'
            for g in prev_attempt.get("gaps", [])
        )
        system += RETRY_PROMPT.format(
            round=round,
            prev_text=prev_attempt.get("transcript", ""),
            prev_gaps=gaps_brief,
        )
    user = (
        f'{_scenario_block(scenario)}学习者刚说的话:\n"{text}"\n\n'
        "请按上面的 SYSTEM 指令，找出他和 native 之间的 gap。"
    )
    return [SystemMessage(content=system), HumanMessage(content=user)]


def _parse_result(raw: str) -> dict:
    raw = raw.replace("```json", "").replace("```", "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        result = CorrectResult.model_validate_json(raw)
    except Exception:
        return {**_EMPTY, "summary": "Evaluation failed. Try again."}
    return result.model_dump()


async def correct_text(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
    link_to: dict | None = None,
) -> dict:
    if not text or len(text.strip().split()) < 3:
        return {**_EMPTY, "summary": "Try saying more — speak in full sentences."}

    messages = _build_messages(text, scenario, prev_attempt, round)

    def _parse(raw: str) -> dict:
        return _parse_result(raw)

    result = await audited_invoke(
        _get_client(), messages,
        kind="correct" if round == 1 else "correct_retry",
        link_to=link_to,
        parser=_parse,
    )
    if result["error"]:
        import logging
        logging.getLogger(__name__).error("correct_text error: %s", result["error"])
        return {**_EMPTY, "summary": "AI service error. Please try again."}
    return result["parsed"] or _EMPTY


async def correct_text_stream(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
    link_to: dict | None = None,
) -> AsyncGenerator[tuple[str, dict], None]:
    """流式版本，yield (event_type, data) 元组：
    - ("chunk", {"text": "..."})  — 原始 token
    - ("done",  {summary, nativeVersion, gaps, progress})
    - ("error", {"message": "..."})
    """
    if not text or len(text.strip().split()) < 3:
        yield "done", {**_EMPTY, "summary": "Try saying more — speak in full sentences."}
        return

    messages = _build_messages(text, scenario, prev_attempt, round)
    started = time.monotonic()
    full_text = ""
    final_metadata: dict | None = None
    err: str | None = None
    parsed: dict | None = None

    try:
        async for chunk in _get_client().astream(messages):
            delta = chunk.content or ""
            if delta:
                full_text += delta
                yield "chunk", {"text": delta}
            # 流末尾的 chunk 可能带 usage_metadata
            if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                final_metadata = chunk.response_metadata

        parsed = _parse_result(full_text)
        yield "done", parsed
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("correct_text_stream error: %s: %s", type(e).__name__, e)
        err = f"{type(e).__name__}: {e}"
        msg = "AI service timed out. Please try again." if "timeout" in type(e).__name__.lower() else f"AI service error ({type(e).__name__}). Please try again."
        yield "error", {"message": msg}

    # 流式结束后异步写 audit（不在 yield 链路上做，免得阻塞前端）
    duration_ms = int((time.monotonic() - started) * 1000)
    tokens = (final_metadata or {}).get("token_usage") or (final_metadata or {}).get("usage_metadata") or {}
    model = (final_metadata or {}).get("model_name") or "?"
    prompt_tok = int(tokens.get("prompt_tokens") or tokens.get("input_tokens") or 0)
    completion_tok = int(tokens.get("completion_tokens") or tokens.get("output_tokens") or 0)
    cost = estimate_text_cost(model, prompt_tok, completion_tok)
    audit_doc = {
        "kind": "correct_stream" if round == 1 else "correct_retry_stream",
        "model": model,
        "request": {
            "systemPrompt": messages[0].content,
            "userPrompt": messages[1].content,
        },
        "response": {"raw": full_text[:8000], "parsed": parsed},
        "tokens": {"prompt": prompt_tok, "completion": completion_tok},
        "cost": float(f"{cost:.6f}"),
        "durationMs": duration_ms,
        "error": err,
        "linkedTo": link_to or {},
        "createdAt": datetime.now(timezone.utc),
    }
    await audit_safe_insert(audit_doc)
