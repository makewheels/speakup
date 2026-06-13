import re
from typing import AsyncGenerator, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import CHAT_MODEL, DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL

_API_TIMEOUT = 60.0
_client: ChatOpenAI | None = None

MAX_ROUNDS = 3


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


SYSTEM_PROMPT = """You are an English coach helping a Chinese adult learner practice SPEAKING in real-life situations.

THE SETUP: the learner is given a scenario (a place, a situation, a mission they must accomplish by speaking English). You receive the scenario and what they actually said.

YOUR JOB: Expose the GAP between what they said and how a native speaker would handle the SAME mission in this scenario. Real spoken English — casual, alive, situation-appropriate. NOT academic, NOT textbook-stiff.

WHAT TO DO:
1. Judge their utterance as a real reply inside the scenario: does it accomplish the mission the way a native would?
2. Identify gaps — phrasing a native would not use, wrong register for the situation, missing moves (e.g. softening a request, stating urgency). Sort by impact.
3. Each gap explains WHY a native says it that way.
4. If they spoke close to native, list at most 1-2 real gaps — an empty gaps list is allowed. Do not pad with trivia.

WHAT NOT TO DO:
- Do NOT change the core IDEA they tried to express — only how it's expressed.
- Do NOT push rare or academic vocabulary.
- Do NOT write meta-talk or encouragements ("Great job!").
- Do NOT correct trivial typos or speech-recognition artifacts if meaning is clear.

LANGUAGE OF FEEDBACK — STRICT:
- `summary`: 必须用中文写，严格不超过25字，一句话。
- `nativeVersion`, gap `original`, gap `better`, gap `example`: 必须用英文写。
- gap `why`: 必须用中文写，遇到英文词汇/短语时可内嵌保留。

OUTPUT: strict JSON only, no markdown fences, no commentary.

{
  "summary": "一句话（中文，最多25字）：最关键的一个差距",
  "nativeVersion": "how a native would say it to accomplish this mission, preserving the learner's intent",
  "gaps": [
    {
      "title": "2-5字中文标签，例如：请求语气、过去时态、催促方式",
      "original": "what they said (exact or close paraphrase, English)",
      "better": "ONE single best native replacement, English only, no slash alternatives",
      "example": "one short sentence a native would actually say in this scenario, using 'better' naturally",
      "why": "1-2句解释为什么母语者这样说（中文，可内嵌英文词）",
      "category": "grammar",
      "saveToReview": true
    }
  ]
}

`category` must be one of: "grammar", "naturalness", "vocabulary", "register".
`saveToReview`: true if memorizing this expression will noticeably improve daily fluency; false for minor one-off style variants."""

RETRY_PROMPT = """

THIS IS ROUND {round} — A RETRY OF THE SAME SCENARIO. Their previous attempt and the gaps you pointed out last time:
Previous attempt: "{prev_text}"
Previous gaps (original -> better): {prev_gaps}

Compare THIS attempt against the previous one. Add a REQUIRED "progress" field to your JSON output:

"progress": {{
  "verdict": "passed | improved | stuck",
  "fixed": ["a suggested expression they successfully used this time — each array item ONE plain string, no arrows"],
  "remaining": ["a suggested expression still not used — each item ONE plain string"],
  "comment": "一句中文点评，不超过20字"
}}

verdict rules:
- "passed": no major gaps left — it now sounds like a native handling this mission. Be generous: minor style nits do not block passing.
- "improved": clearly better but real gaps remain.
- "stuck": the same problems persist.
In "gaps", only list NEW or still-unfixed gaps. Focus on what remains; do not repeat what they already fixed."""


_EMPTY = {
    "summary": "",
    "nativeVersion": "",
    "gaps": [],
    "progress": None,
}


def _scenario_block(scenario: dict | None) -> str:
    if not scenario:
        return ""
    target = ""
    if scenario.get("targetWords"):
        target = f"\nExpressions this learner is training (check if they used them): {', '.join(scenario['targetWords'])}"
    return (
        f"SCENARIO:\n"
        f"- 地点: {scenario.get('where', '')}\n"
        f"- 情境: {scenario.get('story', '')}\n"
        f"- 任务: {scenario.get('mission', '')}{target}\n\n"
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
        f'{_scenario_block(scenario)}The learner said:\n"{text}"\n\n'
        "Expose gaps against how a native speaker would handle this."
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
) -> dict:
    if not text or len(text.strip().split()) < 3:
        return {**_EMPTY, "summary": "Try saying more — speak in full sentences."}

    messages = _build_messages(text, scenario, prev_attempt, round)
    try:
        result: CorrectResult = await _get_client().with_structured_output(CorrectResult).ainvoke(messages)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("correct_text error: %s: %s", type(e).__name__, e)
        return {**_EMPTY, "summary": "AI service error. Please try again."}

    return result.model_dump()


async def correct_text_stream(
    text: str,
    scenario: dict | None = None,
    prev_attempt: dict | None = None,
    round: int = 1,
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
    try:
        full_text = ""
        async for chunk in _get_client().astream(messages):
            delta = chunk.content or ""
            if delta:
                full_text += delta
                yield "chunk", {"text": delta}

        yield "done", _parse_result(full_text)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("correct_text_stream error: %s: %s", type(e).__name__, e)
        msg = "AI service timed out. Please try again." if "timeout" in type(e).__name__.lower() else f"AI service error ({type(e).__name__}). Please try again."
        yield "error", {"message": msg}
