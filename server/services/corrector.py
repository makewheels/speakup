import base64
import re
from typing import AsyncGenerator, Literal

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from config import DASHSCOPE_API_KEY

_API_TIMEOUT = 60.0
_client: ChatOpenAI | None = None


class GapItem(BaseModel):
    title: str = ""
    original: str = ""
    better: str = ""
    example: str = ""
    why: str = ""
    category: Literal["grammar", "naturalness", "vocabulary", "register"] = "vocabulary"
    saveToReview: bool = False


class CorrectResult(BaseModel):
    summary: str = ""
    nativeVersion: str = ""
    gaps: list[GapItem] = Field(default_factory=list)


def _get_client() -> ChatOpenAI:
    global _client
    if _client is None:
        _client = ChatOpenAI(
            openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            openai_api_key=DASHSCOPE_API_KEY,
            model="qwen3.6-plus",
            temperature=0.3,
            max_tokens=2000,
            model_kwargs={"extra_body": {"enable_thinking": False}},
            timeout=_API_TIMEOUT,
        )
    return _client


async def _to_data_url(image_url: str, timeout: float = 20.0) -> str:
    """Fetch the image and inline it as a data URL so DashScope skips its own slow re-fetch."""
    if not image_url or image_url.startswith("data:"):
        return image_url
    if not image_url.startswith(("http://", "https://")):
        return image_url
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            resp = await c.get(image_url)
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip()
            if not mime.startswith("image/"):
                mime = "image/jpeg"
            b64 = base64.b64encode(resp.content).decode("ascii")
            return f"data:{mime};base64,{b64}"
    except Exception:
        return image_url


SYSTEM_PROMPT = """You are an English coach helping a Chinese adult learner.

YOUR JOB: Expose the GAP between what they said and how a native speaker would naturally say it. Target register is "Starbucks-neighbor English" — the way real people talk to each other, not how textbooks teach it. Casual, spoken, alive. NOT academic, NOT formal, NOT "correct but stiff".

WHAT YOU RECEIVE: an image they were describing, and what they actually said in English.

WHAT TO DO:
1. Read their text. Imagine how a native speaker would naturally express the SAME idea while looking at this image.
2. Identify the gaps — where their phrasing differs from natural native speech. Sort by importance (most impactful first).
3. Each gap explains WHY a native says it that way — not just "this is correct, that is wrong".
4. Number of gaps is not fixed. If they spoke close to native, list 1-2 details. If many gaps exist, list all real ones. Do not pad with trivia.

WHAT NOT TO DO:
- Do NOT invent things not in the image or not in their utterance.
- Do NOT change the core IDEA they tried to express — only how it's expressed.
- Do NOT push rare, "impressive", or academic vocabulary. If a native wouldn't say it at a coffee shop, don't suggest it.
- Do NOT write meta-talk ("As an AI tutor...", "Great job!", "Keep it up!"). No encouragements, no role-statements.
- Do NOT correct trivial typos or speech-recognition artifacts if meaning is clear.

LANGUAGE OF FEEDBACK — STRICT:
- `summary`: 必须用中文写，严格不超过25字，一句话，不要列举多个问题。
- `nativeVersion`, gap `original`, gap `better`, gap `example`: 必须用英文写。
- gap `why`: 必须用中文写，遇到英文词汇/短语时可内嵌保留（如 "用 'blurring by' 更有动感"）。

OUTPUT: strict JSON only, no markdown fences, no commentary.

{
  "summary": "一句话（中文，最多25字）：最关键的一个差距是什么",
  "nativeVersion": "rewrite their utterance in natural native daily English, preserving their meaning",
  "gaps": [
    {
      "title": "2-5字中文标签，概括这个差距点的语法/表达规律，例如：复数形式、进行时用法、主谓一致、可数名词、语气词",
      "original": "what they said (exact or close paraphrase, English)",
      "better": "ONE single best native replacement — the way a real person would actually say it in conversation, not the textbook version. English only, no slash alternatives",
      "example": "one short casual sentence a native would actually say out loud, using 'better' naturally. English only",
      "why": "1-2句解释为什么母语者这样说（中文，可内嵌英文词）",
      "category": "grammar",
      "saveToReview": true
    }
  ]
}

`better`: give exactly ONE best option. No slash-separated alternatives. Pick the most natural one.
`category` must be one of: "grammar", "naturalness", "vocabulary", "register".
`saveToReview`: set true if this gap pattern is common enough in daily speech that memorizing it will noticeably improve fluency; set false for minor one-off style variants."""


_EMPTY = {
    "summary": "",
    "nativeVersion": "",
    "gaps": [],
}


async def _build_messages(text: str, image_url: str) -> list:
    if image_url:
        image_payload = await _to_data_url(image_url)
        user_content = [
            {"type": "image_url", "image_url": {"url": image_payload}},
            {"type": "text", "text": f'The student said:\n"{text}"\n\nExpose gaps against a native speaker.'},
        ]
    else:
        user_content = f'The student said:\n"{text}"\n\nExpose gaps against a native speaker.'
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]


def _parse_result(raw: str) -> dict:
    raw = raw.replace("```json", "").replace("```", "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        result = CorrectResult.model_validate_json(raw)
    except Exception:
        return {**_EMPTY, "summary": "Evaluation failed. Try again."}
    return result.model_dump()


async def correct_text(text: str, image_url: str = "") -> dict:
    if not text or len(text.strip().split()) < 3:
        return {**_EMPTY, "summary": "Try saying more — describe what you see in detail."}

    messages = await _build_messages(text, image_url)
    try:
        result: CorrectResult = await _get_client().with_structured_output(CorrectResult).ainvoke(messages)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("correct_text error: %s: %s", type(e).__name__, e)
        return {**_EMPTY, "summary": "AI service error. Please try again."}

    return result.model_dump()


async def correct_text_stream(
    text: str, image_url: str = ""
) -> AsyncGenerator[tuple[str, dict], None]:
    """流式版本，yield (event_type, data) 元组：
    - ("chunk", {"text": "..."})  — 原始 token
    - ("done",  {summary, nativeVersion, gaps})
    - ("error", {"message": "..."})
    """
    if not text or len(text.strip().split()) < 3:
        yield "done", {**_EMPTY, "summary": "Try saying more — describe what you see in detail."}
        return

    messages = await _build_messages(text, image_url)
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
