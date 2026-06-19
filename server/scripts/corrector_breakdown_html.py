"""可视化 corrector（评估用户口语）的 LLM 调用——拿用户那段 WiFi router 输入做真实例子。

跑一次：
  - 用户构造的"输入"：scenario（故事/任务/提示）+ 用户说的话 transcript
  - 完整组装 SYSTEM + USER prompt
  - 调真 LLM
  - 拿到结构化 JSON 返回（summary / nativeVersion / gaps / score / progress）
  - 渲染单页 HTML：色块区分"我们传的上下文"vs"LLM 给的反馈"
"""

import asyncio
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage

from db.connection import connect_db
from services.corrector import SYSTEM_PROMPT, _build_messages, _get_client, _parse_result

OUT_PATH = "/tmp/corrector_breakdown.html"

# SYSTEM_PROMPT 的中文翻译（仅用于展示，实际发给 LLM 的是英文原文，不改 production 行为）
SYSTEM_PROMPT_CN = """你是英语教练，帮助一个中国成年学习者练习真实生活场景下的英语口语。

设定：学习者拿到一个场景题（地点、情境、需要用英语完成的任务）。你拿到这个场景，以及他实际说出来的话。

你的工作：找出他说的内容跟"native speaker 在同样场景下完成同样任务"之间的差距。
真实口语英语——口语化、有生气、贴合场合；不是教科书式的、不是学术式的。

要做的事：
1. 把他的话当成场景里的真实回应来判断：他完成任务的方式是不是 native 会用的？
2. 找出 gaps —— native 不会用的措辞、跟场合不对的语体、缺失的表达动作（比如软化请求、表明紧迫）。按影响力排序。
3. 每个 gap 解释 native 为什么这么说。
4. **最多列 2 个 gaps** —— 只选影响最大的。可以一个都没有。偏向小而精的改动（通常 1-3 个词），不要凑数。

不要做的事：
- 不要改他想表达的核心意思——只改"怎么表达"。
- 不要推荐生僻词或学术词。
- 不要写场面话或鼓励（"做得真棒！"）。
- 含义清晰的小笔误或语音识别杂音不要纠正。

硬性约束：
- `nativeVersion` 是对学习者原话的直接改写——保留他的内容和意图，只改"怎么说"。不要凭空换成完全不同的答案或加他没想表达的内容。
- `nativeVersion` 最多 3 句——紧凑，是 native 真会大声说出来的话。
- 每个 gap 的 `better` 必须**逐字出现**在 `nativeVersion` 里，这样 gaps 和 native version 严格对得上。

打分（按 IELTS 口语 band）：
- `score`: 0-9 之间的数，以 0.5 为步进（比如 5.0、6.5、7.0）。以 IELTS 考官口吻评这一段：流利度+连贯、词汇、语法宽度+准确度、任务完成度。要实事求是——典型中国学习者在 5.0-6.5；7.5+ 留给真正接近 native 的自然英语。短的、破的、跑题的，分要打低。

反馈语言（严格规定）：
- `summary`: 必须中文，严格不超过 25 字，一句话。
- `nativeVersion` / gap `original` / `better` / `example`: 必须英文。
- gap `why`: 必须中文（可嵌英文词）。对照式解释——既点明"原说法哪里不好"（生硬/语法错/语体不对/不自然），又说"地道说法为什么更好"。例如："but 太生硬，actually 更自然地引出纠正" / "had had 是时态错误，应该用一般过去时"。一句话，尽量简短（≤40 字），不要长篇、不要举多例。

输出：严格 JSON，无 markdown 围栏，无任何解说。

{
  "summary": "一句话（中文，最多 25 字）：最关键的一个差距",
  "nativeVersion": "学习者原话的直接改写 —— native、自然，最多 3 句；每个 gap 的 better 必须逐字出现",
  "score": 6.5,
  "gaps": [
    {
      "title": "2-5 字中文标签，例如：请求语气、过去时态、催促方式",
      "original": "他说的话（原文或近似改写，英文）",
      "better": "一个 native 替换说法（最好 1-3 个词的小修），仅英文，不要 slash 选项 —— 必须逐字出现在 nativeVersion 里",
      "example": "一句 native 在该场景里真会说的话，自然用上 better",
      "why": "中文对照解释（≤40 字）：原说法哪里不好 + 地道说法为什么更好",
      "category": "grammar",
      "saveToReview": true
    }
  ]
}

category 必须是：grammar / naturalness / vocabulary / register 之一。
saveToReview: 如果记住这个表达能明显提升日常流利度，true；只是一次性的风格差异，false。"""

# 拿用户刚才在 WiFi router 那道遇到的真实输入做演示
DEMO_SCENARIO = {
    "where": "家中卧室 · 周末上午",
    "story": "WiFi 突然彻底没信号，路由器灯还亮着但完全上不了网，你想打电话叫师傅明早上门看看。",
    "mission": "跟客服说清问题并约师傅",
    "points": [
        "灯都亮但完全连不上网",
        "明早 9 点在家方便上门",
    ],
}

DEMO_TRANSCRIPT = (
    "The Wi-Fi router is not working, but the the light on it is green and it's all red. "
    "I'm here in tomorrow. Can you send up a thief to help me it out?"
)


def _render_html(messages: list, raw_response: str, parsed: dict, token_usage: dict) -> str:
    sys_msg = messages[0].content
    user_msg = messages[1].content

    gaps_html = ""
    for i, g in enumerate(parsed.get("gaps", []) or [], 1):
        gaps_html += f"""
<div class="gap-card">
  <div class="gap-num">#{i}</div>
  <div class="gap-row"><span class="gap-label">用户说</span><code class="gap-orig">{html.escape(g.get('original',''))}</code></div>
  <div class="gap-row"><span class="gap-label">地道说</span><code class="gap-better">{html.escape(g.get('better',''))}</code></div>
  <div class="gap-row"><span class="gap-label">为什么</span><span class="gap-why">{html.escape(g.get('why',''))}</span></div>
</div>"""

    score = parsed.get("score", "?")
    summary = html.escape(parsed.get("summary", "") or "")
    native_version = html.escape(parsed.get("nativeVersion", "") or "")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Corrector LLM 调用拆解</title>
<style>
  body {{
    font-family: -apple-system, "PingFang SC", sans-serif;
    background: #fafafa;
    color: #1a1a1a;
    max-width: 960px;
    margin: 0 auto;
    padding: 24px 16px;
    font-size: 16px;
    line-height: 1.7;
  }}
  h1 {{ font-size: 22px; color: #333; margin: 0 0 8px; }}
  h2 {{ font-size: 18px; color: #333; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #e5e7eb; }}
  .legend {{ display: flex; gap: 16px; margin: 12px 0 24px; font-size: 14px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .swatch {{ display: inline-block; width: 14px; height: 14px; border-radius: 3px; }}
  .swatch.input {{ background: #dbeafe; border: 1px solid #1e40af; }}
  .swatch.output {{ background: #fed7aa; border: 1px solid #9a3412; }}
  .hl-input {{ background: #dbeafe; color: #1e40af; padding: 1px 4px; border-radius: 3px; font-weight: 600; }}
  .hl-output {{ background: #fed7aa; color: #9a3412; padding: 1px 4px; border-radius: 3px; }}
  pre {{
    background: white; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 16px; white-space: pre-wrap; word-break: break-word;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 13px; line-height: 1.55; color: #333;
    max-height: 500px; overflow-y: auto;
  }}
  .meta {{ color: #888; font-size: 13px; margin: 4px 0 16px; }}
  .quote {{
    background: #dbeafe; padding: 14px 18px; border-radius: 8px; font-size: 17px;
    border-left: 4px solid #2563eb; margin: 12px 0;
  }}
  .gap-card {{
    background: white; padding: 14px 18px; border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 14px;
    border-left: 4px solid #ea580c;
    position: relative;
  }}
  .gap-num {{
    position: absolute; top: 14px; right: 18px;
    color: #ea580c; font-weight: 700; font-size: 14px;
  }}
  .gap-row {{ margin: 6px 0; display: flex; gap: 10px; }}
  .gap-label {{ color: #888; font-size: 13px; min-width: 60px; }}
  .gap-orig {{ background: #fee2e2; color: #b91c1c; padding: 2px 6px; border-radius: 4px; font-family: ui-monospace, monospace; }}
  .gap-better {{ background: #d1fae5; color: #065f46; padding: 2px 6px; border-radius: 4px; font-family: ui-monospace, monospace; }}
  .gap-why {{ color: #555; font-size: 14px; }}
  .summary-card {{
    background: #fed7aa; padding: 14px 18px; border-radius: 8px;
    border-left: 4px solid #ea580c; margin: 12px 0; font-size: 15px;
  }}
  .native-card {{
    background: #d1fae5; padding: 14px 18px; border-radius: 8px;
    border-left: 4px solid #059669; margin: 12px 0; font-size: 17px;
    font-family: -apple-system, sans-serif;
  }}
  .score-big {{
    display: inline-block; background: #fed7aa; color: #9a3412;
    padding: 6px 16px; border-radius: 8px; font-size: 22px; font-weight: 700;
  }}
</style>
</head>
<body>

<h1>Corrector LLM 调用拆解（用户答完一题之后跑的反馈）</h1>
<div class="meta">model: {html.escape(token_usage.get("model_name", "?"))} ·
prompt {token_usage.get("prompt_tokens", "?")} tok · completion {token_usage.get("completion_tokens", "?")} tok</div>

<div class="legend">
  <div class="legend-item"><span class="swatch input"></span>蓝色 = 我们传的上下文（场景 + 用户说的话）</div>
  <div class="legend-item"><span class="swatch output"></span>橙色 = LLM 给的反馈</div>
</div>

<h2>① 我们传给 LLM 的场景（来自 scenarios 集合）</h2>
<div class="quote">
<strong>地点</strong>：{html.escape(DEMO_SCENARIO["where"])}<br>
<strong>情景</strong>：{html.escape(DEMO_SCENARIO["story"])}<br>
<strong>任务</strong>：{html.escape(DEMO_SCENARIO["mission"])}<br>
<strong>提示</strong>：
<ul>{"".join(f"<li>{html.escape(p)}</li>" for p in DEMO_SCENARIO["points"])}</ul>
</div>

<h2>② 用户说的话 transcript（语音识别转文字）</h2>
<div class="quote" style="font-family: ui-monospace, monospace; font-size: 15px; line-height: 1.6;">
{html.escape(DEMO_TRANSCRIPT)}
</div>

<h2>③ 完整 SYSTEM PROMPT（一大段固定指令，告诉 LLM 它是英语教练 / 怎么找 gap / 怎么打分）</h2>
<p style="font-size:13px;color:#888;">实际发给 LLM 的是英文原文（生产环境不变），下方是中文翻译版方便你阅读。</p>
<details>
  <summary style="cursor:pointer;color:#2563eb;font-size:13px;margin-bottom:8px;">▶ 点这里展开查看英文原文</summary>
  <pre>{html.escape(sys_msg)}</pre>
</details>
<pre style="background:#fffbeb;border-color:#fde68a;">{html.escape(SYSTEM_PROMPT_CN)}</pre>

<h2>④ USER MESSAGE（场景 + transcript 拼接成的）</h2>
<pre>{html.escape(user_msg)}</pre>

<h2>⑤ LLM 真实返回的反馈（每一项都是它自己评的）</h2>

<div style="margin-bottom:8px;font-size:14px;color:#666;">IELTS 口语 band 分</div>
<div class="score-big">{score} / 9</div>

<div style="margin-top:18px;font-size:14px;color:#666;">一句话总评</div>
<div class="summary-card">{summary}</div>

<div style="margin-top:18px;font-size:14px;color:#666;">native version（地道说法重写）</div>
<div class="native-card">{native_version}</div>

<div style="margin-top:18px;font-size:14px;color:#666;">gaps（识别到的具体错处，按严重度排）</div>
{gaps_html if gaps_html else "<p style='color:#888;'>（LLM 没给出具体 gap）</p>"}

<h2>⑥ 完整 raw JSON（开发者参考）</h2>
<pre>{html.escape(json.dumps(parsed, ensure_ascii=False, indent=2))}</pre>

</body>
</html>"""


async def main():
    await connect_db()
    messages = _build_messages(DEMO_TRANSCRIPT, scenario=DEMO_SCENARIO, round=1)

    print("调 LLM...")
    # corrector 用 with_structured_output，这里直接用 _get_client 走原始路径方便取 token usage
    resp = await _get_client().with_structured_output(method="json_mode").ainvoke(messages)
    # 上面会返回 dict（结构化），但我们想看 raw 也行——退回普通调用
    resp = await _get_client().ainvoke(messages)
    raw = resp.content
    parsed = _parse_result(raw)

    token_usage = {
        "model_name": resp.response_metadata.get("model_name", "?"),
        "prompt_tokens": resp.response_metadata.get("token_usage", {}).get("prompt_tokens", "?"),
        "completion_tokens": resp.response_metadata.get("token_usage", {}).get("completion_tokens", "?"),
    }

    Path(OUT_PATH).write_text(
        _render_html(messages, raw, parsed, token_usage),
        encoding="utf-8",
    )
    print(f"\n→ open {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
