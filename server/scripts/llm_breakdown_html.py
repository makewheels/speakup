"""可视化"我们给 LLM 什么 / LLM 还给我们什么"——拆解一次真实调用。

跑一次：
  - 从 yaml 随机抽一个坐标
  - 完整组装 prompt（含坐标插值后的样子）
  - 调真 LLM
  - 拿到 JSON 返回
  - 渲染单页 HTML：色块区分"我们给的"vs"LLM 给的"
"""

import asyncio
import html
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage

from db.connection import connect_db
from services.scenario_service import PUBLIC_GEN_PROMPT, _get_client, load_taxonomy

OUT_PATH = "/tmp/llm_breakdown.html"


def _highlight_inputs(prompt_text: str, coord: dict) -> str:
    """在 prompt 文本里把坐标值用蓝色高亮，让用户一眼看出哪些字段是变量插值。"""
    out = html.escape(prompt_text)
    values = [
        coord["note"] or "(空)",
        coord["subName"],
        coord["domainName"],
        coord["kind"],
        str(coord["difficulty"]),
    ]
    for v in values:
        v_esc = html.escape(str(v))
        if v_esc and v_esc in out:
            out = out.replace(v_esc, f'<span class="hl-input">{v_esc}</span>', 1)
    return out


def _render_html(coord: dict, system_prompt: str, user_prompt: str,
                 raw_response: str, parsed: dict, token_usage: dict) -> str:
    sys_html = _highlight_inputs(system_prompt, coord)
    coord_table = "".join(
        f'<tr><td>{html.escape(k)}</td><td><code class="hl-input">{html.escape(str(v))}</code></td></tr>'
        for k, v in [
            ("域 domain", coord["domainName"]),
            ("子场景 sub", coord["subName"]),
            ("subId", coord["subId"]),
            ("kind", coord["kind"]),
            ("难度 difficulty", f"{coord['difficulty']}/3"),
            ("note 提示", coord["note"] or "(空)"),
        ]
    )
    output_table = "".join(
        f'<tr><td>{html.escape(k)}</td><td><code class="hl-output">{html.escape(json.dumps(v, ensure_ascii=False))}</code></td></tr>'
        for k, v in parsed.items()
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>LLM 调用拆解</title>
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
  .legend {{
    display: flex;
    gap: 16px;
    margin: 12px 0 24px;
    font-size: 14px;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .swatch {{ display: inline-block; width: 14px; height: 14px; border-radius: 3px; }}
  .hl-input {{ background: #dbeafe; color: #1e40af; padding: 1px 4px; border-radius: 3px; font-weight: 600; }}
  .hl-output {{ background: #fed7aa; color: #9a3412; padding: 1px 4px; border-radius: 3px; }}
  .swatch.input {{ background: #dbeafe; border: 1px solid #1e40af; }}
  .swatch.output {{ background: #fed7aa; border: 1px solid #9a3412; }}
  table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
  th {{ background: #f9fafb; font-weight: 600; color: #555; font-size: 14px; }}
  td:first-child {{ width: 30%; color: #666; font-size: 14px; }}
  pre {{
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 13px;
    line-height: 1.55;
    color: #333;
    max-height: 600px;
    overflow-y: auto;
  }}
  code {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px; }}
  .meta {{ color: #888; font-size: 13px; margin: 4px 0 16px; }}
  .three-section {{ margin: 32px 0; padding: 20px; background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  .three-section h3 {{ margin: 0 0 8px; font-size: 14px; color: #2563eb; letter-spacing: 0.5px; }}
  .three-section .three-content {{ font-size: 17px; }}
  .three-section .three-content.mission {{ font-weight: 600; }}
  .three-section ul {{ margin: 0; padding-left: 22px; }}
</style>
</head>
<body>

<h1>LLM 调用拆解</h1>
<div class="meta">model: {html.escape(token_usage.get("model_name", "?"))} ·
prompt {token_usage.get("prompt_tokens", "?")} tok · completion {token_usage.get("completion_tokens", "?")} tok</div>

<div class="legend">
  <div class="legend-item"><span class="swatch input"></span>蓝色 = 我们给的（yaml 坐标 + 模板）</div>
  <div class="legend-item"><span class="swatch output"></span>橙色 = LLM 自己生成的</div>
</div>

<h2>① 我们随机抽到的坐标（来自 yaml）</h2>
<table>
  <thead><tr><th>字段</th><th>值</th></tr></thead>
  <tbody>{coord_table}</tbody>
</table>
<p style="font-size:13px;color:#888;margin-top:8px;">这一组 5 个值是我们的"骨架"——按 yaml 文件 + 系统 shuffle 算法选出来。LLM 必须严格在这个坐标内编故事，不许改 domain / sub / kind / difficulty。</p>

<h2>② 完整发给 LLM 的 system prompt（蓝色字是上面的坐标值插进去的位置）</h2>
<pre>{sys_html}</pre>

<h2>③ user message</h2>
<pre>{html.escape(user_prompt)}</pre>

<h2>④ LLM 真实返回的 JSON（每一项都是它自己想的）</h2>
<table>
  <thead><tr><th>字段</th><th>LLM 生成的值</th></tr></thead>
  <tbody>{output_table}</tbody>
</table>
<p style="font-size:13px;color:#888;margin-top:8px;">title / where / story / mission / points / imagePrompt 这 6 项全是 LLM 现想的，每次跑都不一样。imagePrompt 进万相，得到图片；其余字段直接进 MongoDB scenarios 集合。</p>

<h2>⑤ 渲染成最终用户看到的题目</h2>
<div class="three-section">
  <h3>情景</h3>
  <div class="three-content">{html.escape(parsed.get("story", ""))}</div>
</div>
<div class="three-section">
  <h3>任务</h3>
  <div class="three-content mission">{html.escape(parsed.get("mission", ""))}</div>
</div>
<div class="three-section">
  <h3>提示</h3>
  <ul>{"".join(f"<li>{html.escape(p)}</li>" for p in parsed.get("points", []))}</ul>
</div>
<p style="font-size:13px;color:#888;margin-top:8px;">前端把 LLM 输出的 story / mission / points 三个字段直接渲染成上面这种卡片。图片单独走 imagePrompt → 万相 → OSS。</p>

</body>
</html>"""


async def main():
    await connect_db()
    tax = load_taxonomy()
    all_subs = []
    for d in tax["domains"]:
        for s in d["subs"]:
            all_subs.append({
                "domainName": d["domain"],
                "domainShort": d["short"],
                "subId": s["id"],
                "subName": s["sub"],
                "kind": s["kind"],
                "difficulty": s["difficulty"],
                "note": s.get("note", ""),
            })
    coord = random.choice(all_subs)
    print(f"随机抽到：{coord['domainName']} / {coord['subName']} ({coord['subId']})")

    system_prompt = PUBLIC_GEN_PROMPT.format(
        domain=coord["domainName"],
        sub=coord["subName"],
        kind=coord["kind"],
        difficulty=coord["difficulty"],
        note=coord["note"],
    )
    user_prompt = "出一道。"

    print("调 LLM...")
    resp = await _get_client().ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    raw = resp.content
    # 清理 markdown 围栏 / think 标签
    import re
    cleaned = re.sub(r"```(json)?", "", raw)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    parsed = json.loads(cleaned)

    token_usage = {
        "model_name": resp.response_metadata.get("model_name", "?"),
        "prompt_tokens": resp.response_metadata.get("token_usage", {}).get("prompt_tokens", "?"),
        "completion_tokens": resp.response_metadata.get("token_usage", {}).get("completion_tokens", "?"),
    }

    Path(OUT_PATH).write_text(
        _render_html(coord, system_prompt, user_prompt, raw, parsed, token_usage),
        encoding="utf-8",
    )
    print(f"\n→ open {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
