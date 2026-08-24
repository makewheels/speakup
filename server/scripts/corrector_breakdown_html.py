"""用一条固定口语输入调用当前 corrector，并生成可人工审阅的单页 HTML。

页面同时展示实际 SYSTEM/USER 消息和结构化结果（summary / score / gaps / progress），
用于检查 gap 是否来自原话、上下配对范围是否合适。脚本只调用一次模型。
"""

import asyncio
import html
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.corrector import _build_messages, _get_client, _parse_result


DEMO_SCENARIO = {
    "where": "家中卧室 · 周末上午",
    "story": "WiFi 突然彻底没信号，路由器灯还亮着但完全上不了网，你想叫师傅明早上门看看。",
    "mission": "跟客服说清问题并约师傅",
    "points": ["灯都亮但完全连不上网", "明早 9 点在家方便上门"],
}
DEMO_TRANSCRIPT = (
    "The Wi-Fi router is not working, but the the light on it is green and it's all red. "
    "I'm here in tomorrow. Can you send up a thief to help me it out?"
)


def _gap_cards(gaps: list[dict]) -> str:
    cards = []
    for index, gap in enumerate(gaps, 1):
        cards.append(f"""
        <article class="gap">
          <strong>建议 {index} · {html.escape(gap.get("title", ""))}</strong>
          <div class="pair said"><span>你说的</span><p>{html.escape(gap.get("original", "")) or "（任务信息未提及）"}</p></div>
          <div class="pair better"><span>这样说</span><p>{html.escape(gap.get("better", ""))}</p></div>
          <p class="why">{html.escape(gap.get("why", ""))}</p>
        </article>
        """)
    return "".join(cards) or '<p class="muted">本次没有 gap。</p>'


def _render(messages: list, raw: str, parsed: dict, metadata: dict) -> str:
    scenario = html.escape(json.dumps(DEMO_SCENARIO, ensure_ascii=False, indent=2))
    model = html.escape(str(metadata.get("model_name") or "?"))
    score = html.escape(str(parsed["score"])) if parsed.get("score") is not None else "—"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>表达反馈调用审阅</title>
<style>
  :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
  body {{ max-width: 900px; margin: 0 auto; padding: 28px 18px 60px; line-height: 1.6; }}
  h1 {{ font-size: 24px; }} h2 {{ margin-top: 32px; font-size: 18px; }}
  pre {{ padding: 16px; overflow: auto; border: 1px solid #8885; border-radius: 12px; white-space: pre-wrap; }}
  .meta,.muted {{ color: #777; }} .score {{ font-size: 32px; font-weight: 750; }}
  .gap {{ padding: 16px; margin: 14px 0; border: 1px solid #8885; border-radius: 14px; }}
  .pair {{ display: grid; grid-template-columns: 72px 1fr; gap: 10px; margin-top: 12px; }}
  .pair span {{ font-size: 13px; color: #777; }} .pair p {{ margin: 0; }}
  .said p {{ color: #b44; }} .better p {{ color: #18794e; font-weight: 650; }}
  .why {{ margin: 12px 0 0 82px; color: #777; }}
</style>
</head>
<body>
  <h1>表达反馈调用审阅</h1>
  <p class="meta">model: {model} · 单次真实调用</p>

  <h2>输入场景</h2><pre>{scenario}</pre>
  <h2>用户原话</h2><pre>{html.escape(DEMO_TRANSCRIPT)}</pre>
  <h2>SYSTEM 消息</h2><pre>{html.escape(messages[0].content)}</pre>
  <h2>USER 消息</h2><pre>{html.escape(messages[1].content)}</pre>

  <h2>结果</h2>
  <div class="score">{score} / 9</div>
  <p>{html.escape(parsed.get("summary", ""))}</p>
  {_gap_cards(parsed.get("gaps") or [])}

  <h2>结构化 JSON</h2><pre>{html.escape(json.dumps(parsed, ensure_ascii=False, indent=2))}</pre>
  <h2>原始返回</h2><pre>{html.escape(raw)}</pre>
</body>
</html>"""


async def main() -> None:
    messages = _build_messages(DEMO_TRANSCRIPT, scenario=DEMO_SCENARIO, round=1)
    response = await _get_client().ainvoke(messages)
    raw = str(response.content)
    parsed = _parse_result(raw)
    with tempfile.NamedTemporaryFile(prefix="speakup-corrector-", suffix=".html", delete=False) as temp_file:
        output = Path(temp_file.name)
    output.write_text(_render(messages, raw, parsed, response.response_metadata), encoding="utf-8")
    print(f"open {output}")


if __name__ == "__main__":
    asyncio.run(main())
