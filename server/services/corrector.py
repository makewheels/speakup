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


SYSTEM_PROMPT = """You are a friendly English tutor helping a Chinese student. You can SEE the image they described.

1. Briefly describe what you actually see in the image (as reference)
2. Correct their grammar, vocabulary, and expression errors
3. Point out things in the image they missed
4. Suggest richer vocabulary they could use

Give ALL feedback in English (corrections, tips, reasons). Use Chinese only for complex grammar concepts.

Respond with ONLY valid JSON:
{
  "whatISee": "what is actually in the image (2-3 sentences)",
  "correctedText": "their corrected version",
  "corrections": [
    { "original": "wrong", "corrected": "right", "reason": "why" }
  ],
  "missedElements": ["things they missed in the image"],
  "suggestedVocabulary": ["richer words"],
  "tips": ["study advice in English"]
}"""


async def correct_text(text: str, scene_description: str, image_url: str = "") -> dict:
    if not text or len(text.strip()) < 3:
        return {
            "whatISee": "",
            "correctedText": text,
            "corrections": [],
            "missedElements": [],
            "suggestedVocabulary": [],
            "tips": ["Try to say more! Describe what you see in detail."],
        }

    if image_url:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": f"The student said:\n\"{text}\"\n\nEvaluate against the image."},
            ],
        }]
        model = "qwen3-vl-plus"
    else:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {
            "role": "user", "content": f"The student said:\n\"{text}\"\n\nEvaluate their English.",
        }]
        model = "qwen3.6-plus"

    resp = await _get_client().chat.completions.create(
        model=model, messages=messages, temperature=0.3, max_tokens=2000,
    )

    raw = resp.choices[0].message.content or ""
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "whatISee": "", "correctedText": text,
            "corrections": [], "missedElements": [], "suggestedVocabulary": [],
            "tips": ["Sorry, evaluation failed. Please try again."],
        }

    return {
        "whatISee": result.get("whatISee", ""),
        "correctedText": result.get("correctedText", text),
        "corrections": result.get("corrections", []),
        "missedElements": result.get("missedElements", []),
        "suggestedVocabulary": result.get("suggestedVocabulary", []),
        "tips": result.get("tips", []),
    }
