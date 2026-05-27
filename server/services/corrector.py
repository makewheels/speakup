import base64
import json
import re
from typing import AsyncGenerator

import httpx
from openai import AsyncOpenAI

from config import DASHSCOPE_API_KEY

_client = None

_API_TIMEOUT = 60.0


def _get_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=DASHSCOPE_API_KEY,
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

YOUR JOB: Expose the GAP between what they said and how a native speaker would naturally say it. Target register is "Starbucks-neighbor English" — natural daily speech, not BBC, not literary, not GRE.

WHAT YOU RECEIVE: an image they were describing, and what they actually said in English.

WHAT TO DO:
1. Read their text. Imagine how a native speaker would naturally express the SAME idea while looking at this image.
2. Identify the gaps — where their phrasing differs from natural native speech. Sort by importance (most impactful first).
3. Each gap explains WHY a native says it that way — not just "this is correct, that is wrong".
4. Number of gaps is not fixed. If they spoke close to native, list 1-2 details. If many gaps exist, list all real ones. Do not pad with trivia.

WHAT NOT TO DO:
- Do NOT invent things not in the image or not in their utterance.
- Do NOT change the core IDEA they tried to express — only how it's expressed.
- Do NOT push rare or "impressive" vocabulary. Daily natural language only.
- Do NOT write meta-talk ("As an AI tutor...", "Great job!", "Keep it up!"). No encouragements, no role-statements.
- Do NOT correct trivial typos or speech-recognition artifacts if meaning is clear.

LANGUAGE OF FEEDBACK — STRICT:
- `summary`: 必须用中文写。
- `nativeVersion`, gap `original`, gap `better`, gap `example`: 必须用英文写。
- gap `why`: 必须用中文写，遇到英文词汇/短语时可内嵌保留（如 "用 'blurring by' 更有动感"）。

OUTPUT: strict JSON only, no markdown fences, no commentary.

{
  "summary": "一句话总结（中文）：学生和母语者的差距在哪，最需要改进的一点是什么",
  "nativeVersion": "rewrite their utterance in natural native daily English, preserving their meaning",
  "gaps": [
    {
      "original": "what they said (exact or close paraphrase, English)",
      "better": "ONE single best native replacement — a word or short phrase, English only, no slash alternatives",
      "example": "one natural sentence using 'better' in context, English",
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
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _parse_result(raw: str) -> dict:
    raw = raw.replace("```json", "").replace("```", "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {**_EMPTY, "summary": "Evaluation failed. Try again."}
    return {
        "summary": result.get("summary", ""),
        "nativeVersion": result.get("nativeVersion", ""),
        "gaps": result.get("gaps", []),
    }


async def correct_text(text: str, image_url: str = "") -> dict:
    if not text or len(text.strip().split()) < 3:
        return {**_EMPTY, "summary": "Try saying more — describe what you see in detail."}

    messages = await _build_messages(text, image_url)
    try:
        resp = await _get_client().chat.completions.create(
            model="qwen3.6-plus",
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            extra_body={"enable_thinking": False},
        )
    except Exception:
        return {**_EMPTY, "summary": "AI service timed out. Please try again."}

    raw = (resp.choices[0].message.content or "")
    return _parse_result(raw)


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
        stream = await _get_client().chat.completions.create(
            model="qwen3.6-plus",
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            extra_body={"enable_thinking": False},
            stream=True,
        )
        full_text = ""
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full_text += delta
                yield "chunk", {"text": delta}

        yield "done", _parse_result(full_text)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("correct_text_stream error: %s: %s", type(e).__name__, e)
        yield "error", {"message": "AI service timed out. Please try again."}
