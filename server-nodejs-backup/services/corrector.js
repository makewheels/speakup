import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  apiKey: process.env.DASHSCOPE_API_KEY,
});

export async function correctText({ text, sceneDescription }) {
  if (!text || text.trim().length < 3) {
    return {
      correctedText: text,
      corrections: [],
      tips: ["你说的太短了，试试描述更多细节吧！"],
      scores: { grammar: 1, vocabulary: 1, completeness: 1, fluency: 1, structure: 1 },
    };
  }

  const systemPrompt = `You are an experienced English tutor helping a Chinese student improve their spoken English.
The student described a scene: "${sceneDescription}".

Your task:
1. Correct grammar, vocabulary, and expression errors. Keep the original meaning.
2. For each error, explain briefly in Chinese.
3. Provide 1-2 general study tips in Chinese.

IMPORTANT: Respond ONLY with valid JSON, no markdown, no code blocks:
{
  "correctedText": "the fully corrected English text",
  "corrections": [
    { "original": "wrong part", "corrected": "corrected part", "reason": "中文解释" }
  ],
  "tips": ["中文学习建议", "..."],
  "scores": {
    "grammar": 3,
    "vocabulary": 3,
    "completeness": 3,
    "fluency": 3,
    "structure": 3
  }
}

Scoring guide (1-5):
- grammar: tense, singular/plural, articles, word order
- vocabulary: word variety, appropriateness
- completeness: how well the description covers the scene
- fluency: natural flow, absence of filler-like patterns
- structure: logical order, use of transitions

Always include at least one positive observation in the tips.`;

  const resp = await client.chat.completions.create({
    model: "qwen3-max",
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: text },
    ],
    temperature: 0.3,
    max_tokens: 2000,
  });

  const raw = resp.choices[0]?.message?.content || "";
  // Qwen sometimes wraps JSON in markdown
  const json = raw.replace(/```json\s*/g, "").replace(/```\s*/g, "").trim();
  const result = JSON.parse(json);

  return {
    correctedText: result.correctedText || text,
    corrections: result.corrections || [],
    tips: result.tips || [],
    scores: {
      grammar: result.scores?.grammar || 3,
      vocabulary: result.scores?.vocabulary || 3,
      completeness: result.scores?.completeness || 3,
      fluency: result.scores?.fluency || 3,
      structure: result.scores?.structure || 3,
    },
  };
}
