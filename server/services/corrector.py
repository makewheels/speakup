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
from services.correction_alignment import normalize_sentence_corrections, split_source_sentences
from services.standard_answer import generate_standard_answer
from services.text_input import is_too_short as _is_too_short
from services.corrector_prompts import (
    FREE_RETRY_PROMPT,
    FREE_SYSTEM_PROMPT,
    RETRY_PROMPT,
    SYSTEM_PROMPT,
)

_API_TIMEOUT = 60.0
_client: ChatOpenAI | None = None
logger = logging.getLogger(__name__)


class GapItem(BaseModel):
    title: str = ""
    original: str = ""
    better: str = ""
    chinese: str = ""
    example: str = ""
    exampleChinese: str = ""
    why: str = ""
    category: Literal["task", "grammar", "naturalness", "vocabulary", "register"] = "vocabulary"
    saveToReview: bool = False


class ProgressInfo(BaseModel):
    verdict: Literal["passed", "improved", "stuck"] = "improved"
    fixed: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    comment: str = ""


class SentenceCorrection(BaseModel):
    sourceId: int
    original: str = ""
    corrected: str = ""


class CorrectResult(BaseModel):
    summary: str = ""
    nativeVersion: str = ""
    sentenceCorrections: list[SentenceCorrection] = Field(default_factory=list)
    standardAnswer: str = ""  # 由独立、只看题目的请求在组合层写入
    note: str = ""  # 旧 API/历史 attempt 兼容；新反馈不再由 LLM 生成
    noteChinese: str = ""
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



_EMPTY = {
    "summary": "",
    "nativeVersion": "",
    "sentenceCorrections": [],
    "standardAnswer": "",
    "note": "",
    "noteChinese": "",
    "score": None,
    "gaps": [],
    "progress": None,
}

# 解析失败兜底文案（correct_text 的自动重试依据它判断）
_PARSE_FAIL = {**_EMPTY, "summary": "AI feedback could not be parsed. Try again."}


def mode_of_scenario(scenario: dict | None) -> str:
    """从练习的场景快照推导模式：自由说快照 kind=free；其余（含旧数据）按场景题。"""
    return "free" if scenario and scenario.get("kind") == "free" else "scenario"


def _scenario_block(scenario: dict | None) -> str:
    if not scenario or scenario.get("kind") == "free":
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


def _free_topic_block(scenario: dict | None) -> str:
    """自由说模式的话题上下文（可空=无话题自由说）。不给任务要点，只做语言参考。"""
    topic = (scenario or {}).get("freeTopic") or ""
    return f'话题（仅供理解语境，不判完成度）："{topic}"\n' if topic else ""


def _build_messages(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
    mode: str = "scenario",
) -> list:
    free = mode == "free"
    system = FREE_SYSTEM_PROMPT if free else SYSTEM_PROMPT
    if prev_attempt and round > 1:
        gaps_brief = "; ".join(
            f'"{g.get("original", "")}" -> "{g.get("better", "")}"'
            for g in prev_attempt.get("gaps", [])
        )
        system += (FREE_RETRY_PROMPT if free else RETRY_PROMPT).format(
            round=round,
            prev_text=prev_attempt.get("transcript", ""),
            prev_gaps=gaps_brief,
        )
    block = _free_topic_block(scenario) if free else _scenario_block(scenario)
    sentence_lines = "\n".join(
        f"[{index}] {sentence}" for index, sentence in enumerate(split_source_sentences(text))
    )
    user = (
        f"{block}学习者刚说的话（sourceId 必须沿用方括号里的编号）：\n{sentence_lines}\n\n"
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


def _coerce_result(data: dict, free: bool = False, source_text: str = "") -> dict:
    if isinstance(data.get("feedback"), dict):
        data = data["feedback"]
    if isinstance(data.get("result"), dict):
        data = data["result"]

    gaps = []
    for item in data.get("gaps") or []:
        if not isinstance(item, dict):
            continue
        category = item.get("category") if item.get("category") in _CATEGORIES else "vocabulary"
        # 自由说不判任务完成度：模型偶尔仍会吐 task，归一到 naturalness
        if free and category == "task":
            category = "naturalness"
        gaps.append({
            "title": str(item.get("title") or ""),
            "original": str(item.get("original") or ""),
            "better": str(item.get("better") or ""),
            "chinese": str(item.get("chinese") or ""),
            "example": str(item.get("example") or ""),
            "exampleChinese": str(item.get("exampleChinese") or item.get("example_chinese") or ""),
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

    sentence_corrections, native_version = normalize_sentence_corrections(data, source_text)

    return {
        "summary": str(data.get("summary") or ""),
        "nativeVersion": native_version,
        "sentenceCorrections": sentence_corrections,
        # 纠正模型没有权威性：即使越权输出这些字段，也必须在解析边界丢弃。
        "standardAnswer": "",
        "note": "",
        "noteChinese": "",
        "score": score,
        "gaps": gaps,
        "progress": progress,
    }


def _parse_result(raw: str, free: bool = False, source_text: str = "") -> dict:
    raw = _clean_model_json(raw)
    try:
        result = CorrectResult.model_validate(
            _coerce_result(_loads_model_json(raw), free=free, source_text=source_text)
        )
    except Exception:
        logger.warning("corrector parse failed; raw_len=%d raw_start=%r", len(raw), raw[:200])
        return dict(_PARSE_FAIL)
    return result.model_dump()


def _is_usable(result: dict | None) -> bool:
    return bool(result and ((result.get("nativeVersion") or "").strip() or result.get("gaps")))


async def _correct_text_only(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
    link_to: dict | None = None,
) -> dict:
    if _is_too_short(text):
        return {**_EMPTY, "summary": "Try saying more — speak in full sentences."}

    # 模式由会话快照携带（free 会话快照 kind=free），不另加参数，保持函数签名精简
    mode = mode_of_scenario(scenario)
    messages = _build_messages(text, scenario, prev_attempt, round, mode)

    def _parse(raw: str) -> dict:
        return _parse_result(raw, free=(mode == "free"), source_text=text)

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


async def _standard_answer_or_empty(scenario: dict | None, link_to: dict | None) -> str:
    """标准答案失败不拖垮纠正主路径；该分支严格只发一次模型请求。"""
    try:
        return await generate_standard_answer(scenario, _get_client(), link_to=link_to)
    except Exception as e:
        logger.warning("standard answer generation failed; degrading to empty: %s", e)
        return ""


async def correct_text(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
    link_to: dict | None = None,
) -> dict:
    """并发执行两条隔离请求，再保持原 API schema 组合返回。"""
    if _is_too_short(text):
        return {**_EMPTY, "summary": "Try saying more — speak in full sentences."}

    correction, standard_answer = await asyncio.gather(
        _correct_text_only(text, scenario, prev_attempt, round, link_to),
        _standard_answer_or_empty(scenario, link_to),
        return_exceptions=True,
    )
    if isinstance(correction, BaseException):
        logger.error("correction branch failed; keeping independent answer: %s", correction)
        correction = {**_EMPTY, "summary": "AI correction unavailable. Independent answer is still available."}
    if isinstance(standard_answer, BaseException):
        logger.warning("standard answer branch failed; keeping correction: %s", standard_answer)
        standard_answer = ""
    return {**correction, "standardAnswer": standard_answer}


async def correct_text_stream(  # noqa: C901, PLR0912, PLR0915
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
    link_to: dict | None = None,
) -> AsyncGenerator[tuple[str, dict], None]:
    """流式版本，yield (event_type, data) 元组：
    - ("chunk", {"text": "..."})  — 原始 token
    - ("done",  {summary, nativeVersion, standardAnswer, gaps, progress})
    - ("error", {"message": "..."})
    """
    if _is_too_short(text):
        yield "done", {**_EMPTY, "summary": "Try saying more — speak in full sentences."}
        return

    mode = mode_of_scenario(scenario)
    messages = _build_messages(text, scenario, prev_attempt, round, mode)
    standard_task = asyncio.create_task(_standard_answer_or_empty(scenario, link_to))
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

        parsed = _parse_result(full_text, free=(mode == "free"), source_text=text) if full_text.strip() else None
        # 流式返空（生产偶发空 content）→ 只降级纠正请求，避免重复生成标准答案。
        if not _is_usable(parsed):
            try:
                fallback = await _correct_text_only(text, scenario, prev_attempt, round, link_to=link_to)
                if _is_usable(fallback):
                    parsed = fallback
            except Exception as e:
                logger.warning("correct_text_stream fallback failed: %s", e)
        if parsed is None:
            parsed = dict(_PARSE_FAIL)
        final_result = {**parsed, "standardAnswer": await standard_task}
        yield "done", final_result
    except Exception as e:
        logger.error("correct_text_stream error: %s: %s", type(e).__name__, e)
        err = f"{type(e).__name__}: {e}"
        try:
            parsed = await _correct_text_only(text, scenario, prev_attempt, round, link_to=link_to)
        except Exception as fallback_error:
            logger.warning("correct_text_stream exception fallback failed: %s", fallback_error)
            parsed = {**_EMPTY, "summary": "AI correction unavailable. Independent answer is still available."}
        standard_answer = await standard_task
        if _is_usable(parsed) or standard_answer:
            yield "done", {**parsed, "standardAnswer": standard_answer}
        else:
            msg = "AI service timed out. Please try again." if "timeout" in type(e).__name__.lower() else f"AI service error ({type(e).__name__}). Please try again."
            yield "error", {"message": msg}
    finally:
        if not standard_task.done():
            standard_task.cancel()
            await asyncio.gather(standard_task, return_exceptions=True)

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
