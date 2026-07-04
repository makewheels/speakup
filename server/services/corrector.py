import re
import time
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL, CHAT_THINKING
from services.llm_audit import (
    _safe_insert as audit_safe_insert,
    audited_invoke,
    content_to_text,
    estimate_text_cost,
)

_API_TIMEOUT = 60.0
_client: ChatOpenAI | None = None
logger = logging.getLogger(__name__)

MAX_ROUNDS = 2


class GapItem(BaseModel):
    title: str = ""
    original: str = ""
    better: str = ""
    example: str = ""
    why: str = ""
    category: Literal["task", "grammar", "naturalness", "vocabulary", "register"] = "vocabulary"
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


_CATEGORIES = {"task", "grammar", "naturalness", "vocabulary", "register"}
_VERDICTS = {"passed", "improved", "stuck"}


def _get_client() -> ChatOpenAI:
    global _client
    if _client is None:
        extra_body = {"thinking": {"type": "enabled"}} if CHAT_THINKING else None
        _client = ChatOpenAI(
            openai_api_base=CHAT_BASE_URL,
            openai_api_key=CHAT_API_KEY,
            model=CHAT_MODEL,
            temperature=0.3,
            max_tokens=2000,
            extra_body=extra_body,
            timeout=_API_TIMEOUT,
        )
    return _client


SYSTEM_PROMPT = """你是英语口语教练。根据场景任务和学习者原话，输出严格 JSON，不要 markdown。

先判断任务是否完成；没完成时第一个 gap 必须是 category=task，并给出完成任务该说的话。
只纠真正错误：任务缺失、语法/时态/单复数/词性/语序、Chinglish、用词错误、搭配错误、重复啰嗦、语体不合适。纯口味替换不要列。
gaps 最多 4 条；每个 better 必须逐字出现在 nativeVersion 中。nativeVersion 最多 2 句，保留原意；若任务没完成，要补上必要任务话术。
score 是 IELTS speaking 0-9、0.5 步进。典型中国学习者 5.0-6.5，跑题/太短要低。
语言：summary 中文≤25字；nativeVersion/original/better/example 英文；why 中文≤30字。

JSON schema:
{
  "summary": "",
  "nativeVersion": "",
  "score": 6.0,
  "gaps": [
    {
      "title": "",
      "original": "",
      "better": "",
      "example": "",
      "why": "",
      "category": "task",
      "saveToReview": true
    }
  ],
  "progress": null
}

category 只能是 task / grammar / naturalness / vocabulary / register。
saveToReview：值得反复记忆的表达填 true，一次性任务话术或风格差异填 false。"""

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
- "passed"：任务确实办成了 **且** 没什么大 gap——现在听起来已经像 native 在处理这个任务。要慷慨：小风格瑕疵不阻挡 pass。但任务还没完成（仍有 task gap）就**绝不能** pass。
- "improved"：明显进步但仍有真 gap（含任务还没完全办成）。
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


def _clean_model_json(raw: str) -> str:
    raw = content_to_text(raw)
    raw = raw.replace("```json", "").replace("```", "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        return raw[start:end + 1]
    return raw


def _loads_model_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        pass
    repaired = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(repaired, strict=False)


def _coerce_result(data: dict) -> dict:
    if isinstance(data.get("feedback"), dict):
        data = data["feedback"]
    if isinstance(data.get("result"), dict):
        data = data["result"]

    gaps = []
    for item in data.get("gaps") or []:
        if not isinstance(item, dict):
            continue
        category = item.get("category") if item.get("category") in _CATEGORIES else "vocabulary"
        gaps.append({
            "title": str(item.get("title") or ""),
            "original": str(item.get("original") or ""),
            "better": str(item.get("better") or ""),
            "example": str(item.get("example") or ""),
            "why": str(item.get("why") or ""),
            "category": category,
            "saveToReview": bool(item.get("saveToReview")),
        })

    score = data.get("score")
    if isinstance(score, str):
        match = re.search(r"\d+(?:\.\d+)?", score)
        score = float(match.group(0)) if match else None

    progress = data.get("progress")
    if isinstance(progress, dict):
        verdict = progress.get("verdict")
        if verdict == "needs-work":
            verdict = "improved"
        if verdict not in _VERDICTS:
            verdict = "improved"
        progress = {
            "verdict": verdict,
            "fixed": [str(x) for x in progress.get("fixed") or []],
            "remaining": [str(x) for x in progress.get("remaining") or []],
            "comment": str(progress.get("comment") or ""),
        }
    else:
        progress = None

    return {
        "summary": str(data.get("summary") or ""),
        "nativeVersion": str(data.get("nativeVersion") or data.get("native_version") or ""),
        "score": score,
        "gaps": gaps,
        "progress": progress,
    }


def _parse_result(raw: str) -> dict:
    raw = _clean_model_json(raw)
    try:
        result = CorrectResult.model_validate(_coerce_result(_loads_model_json(raw)))
    except Exception:
        logger.warning("corrector parse failed; raw_len=%d raw_start=%r", len(raw), raw[:200])
        return {**_EMPTY, "summary": "AI feedback could not be parsed. Try again."}
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
    logger.info(
        "correct_text done kind=%s model=%s duration_ms=%s error=%s parsed=%s",
        "correct" if round == 1 else "correct_retry",
        result.get("model"),
        result.get("durationMs"),
        result.get("error"),
        bool(result.get("parsed")),
    )
    if result["error"]:
        logger.error("correct_text error: %s", result["error"])
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
            delta = content_to_text(chunk.content)
            if delta:
                full_text += delta
                yield "chunk", {"text": delta}
            # 流末尾的 chunk 可能带 usage_metadata
            if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                final_metadata = chunk.response_metadata

        parsed = _parse_result(full_text)
        yield "done", parsed
    except Exception as e:
        logger.error("correct_text_stream error: %s: %s", type(e).__name__, e)
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
    logger.info(
        "correct_text_stream done kind=%s model=%s duration_ms=%s prompt_tokens=%s completion_tokens=%s error=%s raw_len=%s",
        audit_doc["kind"],
        model,
        duration_ms,
        prompt_tok,
        completion_tok,
        err,
        len(full_text),
    )
    asyncio.create_task(audit_safe_insert(audit_doc))


# ── 追问对话：用户拿到反馈后，基于本次练习上下文继续问 AI（纯文本流式）──

FOLLOWUP_SYSTEM = """你是这位中国成年学习者的英语口语私教。他刚在一个真实场景里练了口语，你已经给过反馈，现在他想就这次练习继续追问。

像真人教练一样对话：
- 紧扣这次练习的上下文（场景、他说的话、你给的反馈）。他问"为什么这么改""还能怎么说""帮我多举几个例子""这个词什么意思""换个场合怎么说"都好好答。
- 讲解用中文，英文表达/例句用英文（可加简短中文解释）。
- 简洁、直接、给干货；别长篇大论，别堆术语。
- 多鼓励他开口，可以顺手给一两个新例句或小练习让他模仿。
- 纯自然对话：**只输出纯文本**，不要任何 markdown 语法——不要 `**加粗**`、不要 `#` 标题、不要 ``` 代码块。要分点就用「·」或直接换行。"""


def _followup_context(scenario: dict | None, attempt: dict | None) -> str:
    """把场景 + 他说的话 + 已给的反馈拼成上下文，作为对话的背景交给模型。"""
    parts = [_scenario_block(scenario).strip()] if scenario else []
    if attempt:
        parts.append(f'他这次说的话："{attempt.get("transcript", "")}"')
        if attempt.get("nativeVersion"):
            parts.append(f'你给的 native 版改写："{attempt["nativeVersion"]}"')
        gaps = attempt.get("gaps") or []
        if gaps:
            lines = "\n".join(
                f'  · [{g.get("category", "")}] {g.get("original", "")} → {g.get("better", "")}（{g.get("why", "")}）'
                for g in gaps
            )
            parts.append(f"你指出的 gaps：\n{lines}")
        if attempt.get("summary"):
            parts.append(f'你的小结：{attempt["summary"]}')
    return "\n".join(p for p in parts if p)


def _build_followup_messages(
    scenario: dict | None, attempt: dict | None, history: list | None, question: str
) -> list:
    system = FOLLOWUP_SYSTEM + "\n\n本次练习的上下文：\n" + _followup_context(scenario, attempt)
    messages: list = [SystemMessage(content=system)]
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content", "")
        if not content:
            continue
        messages.append(AIMessage(content=content) if role == "assistant" else HumanMessage(content=content))
    messages.append(HumanMessage(content=question))
    return messages


async def followup_chat_stream(
    scenario: dict | None,
    attempt: dict | None,
    history: list | None,
    question: str,
    link_to: dict | None = None,
) -> AsyncGenerator[tuple[str, dict], None]:
    """追问对话的流式版本，yield (event_type, data)：
    - ("chunk", {"text": "..."})  — 增量 token
    - ("done",  {"text": "完整回答"})
    - ("error", {"message": "..."})
    """
    if not question or not question.strip():
        yield "error", {"message": "请输入你想问的内容。"}
        return

    messages = _build_followup_messages(scenario, attempt, history, question)
    started = time.monotonic()
    full_text = ""
    final_metadata: dict | None = None
    err: str | None = None

    try:
        async for chunk in _get_client().astream(messages):
            delta = chunk.content or ""
            if delta:
                full_text += delta
                yield "chunk", {"text": delta}
            if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                final_metadata = chunk.response_metadata
        yield "done", {"text": full_text}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("followup_chat_stream error: %s: %s", type(e).__name__, e)
        err = f"{type(e).__name__}: {e}"
        msg = "AI 服务超时，请重试。" if "timeout" in type(e).__name__.lower() else f"AI 服务出错（{type(e).__name__}），请重试。"
        yield "error", {"message": msg}

    duration_ms = int((time.monotonic() - started) * 1000)
    tokens = (final_metadata or {}).get("token_usage") or (final_metadata or {}).get("usage_metadata") or {}
    model = (final_metadata or {}).get("model_name") or "?"
    prompt_tok = int(tokens.get("prompt_tokens") or tokens.get("input_tokens") or 0)
    completion_tok = int(tokens.get("completion_tokens") or tokens.get("output_tokens") or 0)
    cost = estimate_text_cost(model, prompt_tok, completion_tok)
    audit_doc = {
        "kind": "followup_chat",
        "model": model,
        "request": {"systemPrompt": messages[0].content, "userPrompt": question},
        "response": {"raw": full_text[:8000]},
        "tokens": {"prompt": prompt_tok, "completion": completion_tok},
        "cost": float(f"{cost:.6f}"),
        "durationMs": duration_ms,
        "error": err,
        "linkedTo": link_to or {},
        "createdAt": datetime.now(timezone.utc),
    }
    await audit_safe_insert(audit_doc)
