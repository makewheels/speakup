import json
from openai import AsyncOpenAI
from config import DASHSCOPE_API_KEY

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=DASHSCOPE_API_KEY,
        )
    return _client


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
- `summary`, `nativeVersion`, gap `original`/`better`: English.
- gap `why`: default English. Switch to Chinese ONLY when a grammar concept is materially clearer in Chinese. Do not mix within one `why`.

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
        user_content = [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": f'The student said:\n"{text}"\n\nExpose gaps against a native speaker.'},
        ]
    else:
        user_content = f'The student said:\n"{text}"\n\nExpose gaps against a native speaker.'

    resp = await _get_client().chat.completions.create(
        model="qwen3.6-plus",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    raw = (resp.choices[0].message.content or "").replace("```json", "").replace("```", "").strip()

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
