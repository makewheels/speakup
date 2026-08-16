import asyncio, json, logging, re, time
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL, CHAT_THINKING
from services.llm_audit import (
    _safe_insert as audit_safe_insert,
    audited_invoke,
    client_params,
    content_to_text,
    estimate_text_cost,
    extract_usage,
    serialize_messages,
)
from services.text_input import is_too_short as _is_too_short

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


def thinking_extra_body(base_url: str) -> dict:
    """各家 OpenAI 兼容层的 thinking 参数不同，不可以把火山/DeepSeek 私有格式
    透传给百炼。显式关闭可避免短 JSON 任务耗尽 token 后返空。
    DeepSeek 官方 API 不认百炼的 enable_thinking，必须用 thinking.type，
    否则思考模型会先吐几千字 reasoning_content，用户端干等几十秒。"""
    if "volces.com" in base_url or "deepseek.com" in base_url:
        return {"thinking": {"type": "enabled" if CHAT_THINKING else "disabled"}}
    return {"enable_thinking": CHAT_THINKING}


def _get_client() -> ChatOpenAI:
    global _client
    if _client is None:
        _client = ChatOpenAI(
            openai_api_base=CHAT_BASE_URL,
            openai_api_key=CHAT_API_KEY,
            model=CHAT_MODEL,
            temperature=0.3,
            max_tokens=2000,
            extra_body=thinking_extra_body(CHAT_BASE_URL),
            # 流式也回传 token 用量（SSE 末尾 chunk 带 usage），否则审计里 token 恒为 0
            stream_usage=True,
            timeout=_API_TIMEOUT,
        )
    return _client


SYSTEM_PROMPT = """你是英语口语教练。根据场景任务和学习者原话，输出严格 JSON，不要 markdown。

先判断任务是否完成；没完成时第一个 gap 必须是 category=task，并给出完成任务该说的话。
学习者的任务是练英语口语：如果回答主要是中文或其他非英语，即使中文意思对也视为任务未完成，score 不得高于 2.0，第一个 gap 必须是 task。
只纠真正错误：任务缺失、语法/时态/单复数/词性/语序、Chinglish、用词错误、搭配错误、重复啰嗦、语体不合适。纯口味替换不要列。
已经正确、自然的请求可以不列 gap，不要为了“更简洁”而硬改。
gaps 最多 4 条；nativeVersion 最多 2 句，保留原意；若任务没完成，要补上全部必要任务话术和关键信息。

输出 JSON 前做两次硬检查：
1. 每个 gap.better 都必须逐字（忽略大小写）出现在 nativeVersion 中；如果没有，重写 nativeVersion 或删除该 gap。
2. 如果有 task gap，nativeVersion 必须覆盖 scenario mission 和 points 的所有必要信息。
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
saveToReview：值得反复记忆的表达填 true，一次性任务话术或风格差异填 false。

完整示例（场景：在咖啡店点单；学习者说："I want a coffee, big cup"）：
{
  "summary": "任务办成，表达不够自然",
  "nativeVersion": "I'd like a large coffee, please.",
  "score": 5.5,
  "gaps": [
    {
      "title": "更礼貌的点单句式",
      "original": "I want a coffee, big cup",
      "better": "I'd like a large coffee, please",
      "example": "I'd like a latte to go, please.",
      "why": "I'd like 比 I want 礼貌；杯型放名词前",
      "category": "naturalness",
      "saveToReview": true
    }
  ],
  "progress": null
}"""

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

# 解析失败兜底文案（correct_text 的自动重试依据它判断）
_PARSE_FAIL = {**_EMPTY, "summary": "AI feedback could not be parsed. Try again."}


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
        return dict(_PARSE_FAIL)
    return result.model_dump()


def _is_usable(result: dict | None) -> bool:
    return bool(result and ((result.get("nativeVersion") or "").strip() or result.get("gaps")))


async def correct_text(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
    link_to: dict | None = None,
) -> dict:
    if _is_too_short(text):
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
    parsed = result["parsed"] or _EMPTY
    if not _is_usable(parsed):
        # 解析失败/输出为空时自动补救一轮：明确要求只输出 JSON，避免用户白录一遍
        retry_kind = "correct_repair" if round == 1 else "correct_retry_repair"
        retry = await audited_invoke(
            _get_client(),
            messages + [HumanMessage(content="上一次的输出不可用。请严格只输出符合 schema 的 JSON，不要任何其他文字。")],
            kind=retry_kind,
            link_to=link_to,
            parser=_parse,
        )
        retry_parsed = retry["parsed"] or _EMPTY
        if not retry["error"] and _is_usable(retry_parsed):
            logger.info("correct_text repair retry succeeded kind=%s", retry_kind)
            parsed = retry_parsed
    return parsed


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
    if _is_too_short(text):
        yield "done", {**_EMPTY, "summary": "Try saying more — speak in full sentences."}
        return

    messages = _build_messages(text, scenario, prev_attempt, round)
    started = time.monotonic()
    full_text = ""
    final_metadata: dict | None = None
    err: str | None = None
    parsed: dict | None = None
    model = "?"
    prompt_tok = 0
    completion_tok = 0

    final_usage: dict | None = None
    try:
        async for chunk in _get_client().astream(messages):
            delta = content_to_text(chunk.content)
            if delta:
                full_text += delta
                yield "chunk", {"text": delta}
            # finish_reason chunk 带 model_name；开 stream_usage 时 usage 在 chunk 顶层
            if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                final_metadata = chunk.response_metadata
            if getattr(chunk, "usage_metadata", None):
                final_usage = chunk.usage_metadata

        model, prompt_tok, completion_tok = extract_usage(final_metadata, final_usage)
        if prompt_tok or completion_tok:
            yield "usage", {"model": model, "promptTokens": prompt_tok, "completionTokens": completion_tok}

        parsed = _parse_result(full_text) if full_text.strip() else None
        # 流式返空（生产偶发空 content）→ 降级非流式重取，避免结果页只剩用户原话
        if not _is_usable(parsed):
            try:
                fallback = await correct_text(text, scenario, prev_attempt, round, link_to=link_to)
                if _is_usable(fallback):
                    parsed = fallback
            except Exception as e:
                logger.warning("correct_text_stream fallback failed: %s", e)
        if parsed is None:
            parsed = dict(_PARSE_FAIL)
        yield "done", parsed
    except Exception as e:
        logger.error("correct_text_stream error: %s: %s", type(e).__name__, e)
        err = f"{type(e).__name__}: {e}"
        msg = "AI service timed out. Please try again." if "timeout" in type(e).__name__.lower() else f"AI service error ({type(e).__name__}). Please try again."
        yield "error", {"message": msg}

    # 流式结束后异步写 audit（不在 yield 链路上做，免得阻塞前端）
    duration_ms = int((time.monotonic() - started) * 1000)
    cost = estimate_text_cost(model, prompt_tok, completion_tok)
    audit_doc = {
        "kind": "correct_stream" if round == 1 else "correct_retry_stream",
        "model": model,
        "request": {
            "systemPrompt": messages[0].content,
            "userPrompt": messages[1].content if len(messages) > 1 else "",
            "messages": serialize_messages(messages),  # 完整消息列表，一字不少
            "params": client_params(_get_client()),
        },
        "response": {"raw": full_text, "parsed": parsed},  # 完整响应，不截断
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
