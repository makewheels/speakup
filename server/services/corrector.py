import re
import time
import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL, CHAT_THINKING
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


SYSTEM_PROMPT = """你是英语教练，帮助一个中国成年学习者练习真实生活场景下的英语口语。

设定：学习者拿到一个场景题（地点、情境、需要用英语完成的任务）。你拿到这个场景，以及他实际说出来的话。

你的工作：先看他有没有完成场景任务，再找出他说的内容跟"native speaker 在同样场景下完成同样任务"之间的差距。
真实口语英语——口语化、有生气、贴合场合；不是教科书式的、不是学术式的。

要做的事：
1. **先判任务目标（最重要）**：拿场景的「任务/应说到的内容」对照他的话——他真的把任务办成了吗？该说到的点说到了吗？
   - 跑题、答非所问、漏掉关键诉求、根本没完成任务 → 这是**头号问题**：summary 必须点出，并作为**第一个 gap**（`category: "task"`，`original` 放他偏题/缺失处的原话，`better` 给"为完成任务该说的话"，`why` 说明缺了什么、为什么没达成目标）。
   - 目标达成了，才继续看下面的语言问题。
2. **找语言 gaps —— 分清「错」和「纯口味」**：
   - ✅ **必纠（是错，一个都别漏）**：语法/时态/单复数/词性错、语序乱或结构混乱、重复啰嗦（如 "help me to take me a photo" 里多余的 me）、错误搭配/中式英语（Chinglish）、用错词、该有的词漏了。只要 native 听了会觉得不对、困惑、或要重新解析，就必须纠。
   - ❌ **跳过（两种说法都对、纯口味偏好）**：单纯"换个更地道说法"的同义替换（"I'm a software engineer" → "working as a software engineer"、"very nice" → "really friendly"），native 听了完全不皱眉的，放过。
   - 判断口诀：**是「错」就纠，哪怕小**；只是"我更喜欢另一种说法"才忍住。别把真错误当口味放过，也别把口味当错误硬挑。
3. 每个 gap 解释 native 为什么这么说。
4. **gaps 数量按真问题来**：有几个真错误（含任务没达成）就列几个，最多 4 个；没有真错误就空数组。别为纯口味硬凑，但真错误绝不放过。
5. 如果任务办成了、语言也没真错误，summary 用一句鼓励（如"很地道"、"任务完成到位"）。

不要做的事：
- 不要改他想表达的核心意思——只改"怎么表达"。
- 不要推荐生僻词或学术词。
- 不要写场面话或鼓励（"做得真棒！"）。
- 含义清晰的小笔误或语音识别杂音不要纠正。

硬性约束：
- `nativeVersion` 是对学习者原话的直接改写——保留他的内容和意图，只改"怎么说"。**唯一例外**：如果他没完成任务（有 task gap），nativeVersion 要补上完成任务必需的话（让 task gap 的 better 能逐字出现），但仍贴着他的处境，别凭空编无关内容。
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
      "title": "2-5 字中文标签，例如：任务没达成、过去时态、用词重复",
      "original": "他说的话（原文或近似改写，英文）",
      "better": "一个 native 替换说法（最好 1-3 个词的小修），仅英文，不要 slash 选项——必须逐字出现在 nativeVersion 里",
      "example": "一句 native 在该场景里真会说的话，自然用上 better",
      "why": "中文对照解释（≤40 字）：原说法哪里不好 + 地道说法为什么更好",
      "category": "grammar",
      "saveToReview": true
    }
  ]
}

`category` 必须是：task（没完成任务目标）/ grammar / naturalness / vocabulary / register 之一。任务没达成的 gap 用 task，且排在最前。
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
    raw = raw.replace("```json", "").replace("```", "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        return raw[start:end + 1]
    return raw


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
        result = CorrectResult.model_validate(_coerce_result(json.loads(raw)))
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
