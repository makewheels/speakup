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

SYSTEM_PROMPT_TEMPLATE = """You are an experienced English tutor helping a Chinese student improve their spoken English.
The student described a scene: "{scene}".

Your task:
1. Correct grammar, vocabulary, and expression errors. Keep the original meaning.
2. For each error, explain briefly in Chinese.
3. Provide 1-2 general study tips in Chinese.

Respond ONLY with valid JSON, no markdown:
{{
  "correctedText": "the fully corrected English text",
  "corrections": [
    {{ "original": "wrong part", "corrected": "corrected part", "reason": "中文解释" }}
  ],
  "tips": ["中文学习建议"],
  "scores": {{
    "grammar": 3,
    "vocabulary": 3,
    "completeness": 3,
    "fluency": 3,
    "structure": 3
  }}
}}

Scoring guide (1-5):
- grammar: tense, singular/plural, articles, word order
- vocabulary: word variety, appropriateness
- completeness: how well the description covers the scene
- fluency: natural flow
- structure: logical order, use of transitions

Always include at least one positive observation in the tips."""


async def correct_text(text: str, scene_description: str) -> dict:
    if not text or len(text.strip()) < 3:
        return {
            "correctedText": text,
            "corrections": [],
            "tips": ["你说的太短了，试试描述更多细节吧！"],
            "scores": {"grammar": 1, "vocabulary": 1, "completeness": 1, "fluency": 1, "structure": 1},
        }

    resp = await _get_client().chat.completions.create(
        model="qwen3-max",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(scene=scene_description)},
            {"role": "user", "content": text},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    raw = resp.choices[0].message.content or ""
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)

    return {
        "correctedText": result.get("correctedText", text),
        "corrections": result.get("corrections", []),
        "tips": result.get("tips", []),
        "scores": {
            "grammar": result.get("scores", {}).get("grammar", 3),
            "vocabulary": result.get("scores", {}).get("vocabulary", 3),
            "completeness": result.get("scores", {}).get("completeness", 3),
            "fluency": result.get("scores", {}).get("fluency", 3),
            "structure": result.get("scores", {}).get("structure", 3),
        },
    }
