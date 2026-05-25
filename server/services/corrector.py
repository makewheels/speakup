import base64
import json
import re

import httpx
from openai import AsyncOpenAI

from config import DASHSCOPE_API_KEY

_client = None

# DashScope VL 模型调用超时（秒）
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
    """Fetch the image and inline it as a data URL.

    DashScope otherwise re-fetches the original URL on its end; for slow
    image hosts (e.g. loremflickr from mainland China) that re-fetch dominates
    the request. Bypassing it by sending bytes directly is materially faster.
    Falls back to the original URL on any failure so the call still works.
    """
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

LANGUAGE OF FEEDBACK:
- `summary`: Chinese.
- `nativeVersion`, gap `original`/`better`: English.
- gap `why`: Chinese. Keep English terms or short phrases inline when they clarify meaning.

OUTPUT: strict JSON only, no markdown fences, no commentary.

{
  "summary": "one sentence: how close they are to a native, and the main thing to work on",
  "nativeVersion": "rewrite their utterance in natural native daily English, preserving their meaning",
  "gaps": [
    {
      "original": "what they said (exact or close paraphrase)",
      "better": "the native version of that piece",
      "why": "1-2 sentences why a native says it this way",
      "category": "grammar"
    }
  ]
}

`category` must be one of: "grammar", "naturalness", "vocabulary", "register"."""


_EMPTY = {
    "summary": "",
    "nativeVersion": "",
    "gaps": [],
}


async def correct_text(text: str, image_url: str = "") -> dict:
    if not text or len(text.strip().split()) < 3:
        return {
            **_EMPTY,
            "summary": "Try saying more — describe what you see in detail.",
        }

    if image_url:
        # Pre-fetch ourselves and inline as data URL so DashScope skips its own (slow) image fetch.
        image_payload = await _to_data_url(image_url)
        user_content = [
            {"type": "image_url", "image_url": {"url": image_payload}},
            {"type": "text", "text": f'The student said:\n"{text}"\n\nExpose gaps against a native speaker.'},
        ]
    else:
        user_content = f'The student said:\n"{text}"\n\nExpose gaps against a native speaker.'

    try:
        resp = await _get_client().chat.completions.create(
            model="qwen3.6-plus",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=2000,
            extra_body={"enable_thinking": False},
        )
    except Exception:
        return {**_EMPTY, "summary": "AI service timed out. Please try again."}

    raw = (resp.choices[0].message.content or "").replace("```json", "").replace("```", "").strip()
    # qwen3 thinking 模式可能在 content 中混入 <think> 标签
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {
            **_EMPTY,
            "summary": "Evaluation failed. Try again.",
        }

    return {
        "summary": result.get("summary", ""),
        "nativeVersion": result.get("nativeVersion", ""),
        "gaps": result.get("gaps", []),
    }
