"""跨模型对比评测：4 个模型各跑全部 26 个任务，1 trial，出对比 HTML。

跑法：
    cd ~/workspace/learning/speakup/server
    source .venv/bin/activate
    python -m scripts.compare_models

输出：
    /tmp/speakup-models-compare.html  对比报告
    /tmp/speakup-models-compare.json  原始数据
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
SERVER_ROOT = HERE.parent
sys.path.insert(0, str(SERVER_ROOT))

from dotenv import load_dotenv
load_dotenv(SERVER_ROOT / ".env")

from langchain_openai import ChatOpenAI
from pydantic import ValidationError

# 评测代码复用
from evals.harness import load_tasks, apply_graders, Task, TrialResult, TaskReport
import services.corrector as corrector_mod
from services.corrector import correct_text


MODELS = ["glm-5.2", "minimax-m3", "kimi-k2.6", "deepseek-v4-pro"]
BASE_URL = os.getenv("CHAT_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3")
API_KEY = os.getenv("CHAT_API_KEY", "")


def make_client(model: str) -> ChatOpenAI:
    """显式构造客户端，绕过 corrector 内部 _get_client 的单例。"""
    return ChatOpenAI(
        openai_api_base=BASE_URL,
        openai_api_key=API_KEY,
        model=model,
        temperature=0.3,
        max_tokens=2000,
        timeout=180,
    )


async def run_task_with_model(model: str, task: Task) -> TrialResult:
    """换掉 corrector 的全局客户端跑一次。串行调度——同一时刻只一个模型在用单例。"""
    started = time.monotonic()
    corrector_mod._client = make_client(model)
    try:
        result = await correct_text(
            text=task.input["text"],
            scenario=task.input.get("scenario"),
            prev_attempt=task.input.get("prev_attempt"),
            round=task.input.get("round", 1),
            link_to={"eval_compare": model, "task": task.id},
        )
        duration = int((time.monotonic() - started) * 1000)
        tr = TrialResult(trial_index=0, duration_ms=duration, llm_output=result)
    except Exception as e:
        duration = int((time.monotonic() - started) * 1000)
        tr = TrialResult(
            trial_index=0,
            duration_ms=duration,
            llm_output=None,
            error=f"{type(e).__name__}: {e}",
        )
    apply_graders(tr, task)
    return tr


async def run_model(model: str, tasks: list[Task]) -> dict[str, Any]:
    """一个模型跑全部任务（任务内串行，避免单例客户端被并发踩踏）。"""
    print(f"\n▶ {model}  ({len(tasks)} tasks)")
    results = []
    for i, t in enumerate(tasks, 1):
        tr = await run_task_with_model(model, t)
        ok = "✓" if tr.passed else "✗"
        print(f"  {ok}  [{i:2d}/{len(tasks)}] {t.id:35s} {tr.duration_ms:5d}ms")
        results.append({
            "task_id": t.id,
            "task_desc": t.desc,
            "suite": t.source_path.parent.name if t.source_path else "?",
            "passed": tr.passed,
            "duration_ms": tr.duration_ms,
            "error": tr.error,
            "llm_output": tr.llm_output,
            "grader_results": tr.grader_results,
        })
    passed = sum(1 for r in results if r["passed"])
    print(f"  → {model} TOTAL: {passed}/{len(tasks)} ({100*passed/len(tasks):.0f}%)")
    return {"model": model, "tasks": results}


def render_html(all_results: list[dict[str, Any]], tasks: list[Task]) -> str:
    """生成一张对比表：行=任务，列=模型，cell=✓/✗ + 分数 + duration。"""
    # task_id -> {model -> task_result}
    by_task: dict[str, dict[str, dict]] = {}
    for mr in all_results:
        for t in mr["tasks"]:
            by_task.setdefault(t["task_id"], {})[mr["model"]] = t

    models = [mr["model"] for mr in all_results]
    summary_rows = []
    for mr in all_results:
        passed = sum(1 for r in mr["tasks"] if r["passed"])
        total = len(mr["tasks"])
        avg_dur = sum(r["duration_ms"] for r in mr["tasks"]) / max(1, total)
        summary_rows.append({
            "model": mr["model"],
            "passed": passed,
            "total": total,
            "pct": 100 * passed / total,
            "avg_dur_ms": avg_dur,
        })

    # 分 suite 显示
    suites = {}
    for t in tasks:
        s = t.source_path.parent.name if t.source_path else "?"
        suites.setdefault(s, []).append(t)

    def cell(tr: dict | None) -> str:
        if not tr:
            return "<td class='na'>—</td>"
        ok = tr.get("passed")
        out = tr.get("llm_output") or {}
        score = out.get("score")
        dur = tr.get("duration_ms", 0)
        gaps = len(out.get("gaps") or [])
        score_s = f"{score:.1f}" if isinstance(score, (int, float)) else "?"
        # 失败原因 = 第一条 failed grader
        fail_reason = ""
        if not ok:
            fails = [g for g in tr.get("grader_results", []) if not g.get("passed")]
            if fails:
                fail_reason = "<br><span class='reason'>" + ", ".join(g["grader"] for g in fails[:3]) + "</span>"
        cls = "ok" if ok else "fail"
        mark = "✓" if ok else "✗"
        # 详情通过 title 提示
        summary = (out.get("summary") or "").replace('"', '&quot;')[:120]
        return f"<td class='{cls}' title=\"{summary}\">{mark} <b>{score_s}</b> · {gaps}g · {dur}ms{fail_reason}</td>"

    head_models = "".join(f"<th>{m}</th>" for m in models)

    summary_table = """
    <table class='summary'>
      <thead><tr><th>Model</th><th>Passed</th><th>Pass rate</th><th>Avg latency</th></tr></thead>
      <tbody>
    """ + "".join(
        f"<tr><td><b>{r['model']}</b></td>"
        f"<td>{r['passed']}/{r['total']}</td>"
        f"<td><b>{r['pct']:.0f}%</b></td>"
        f"<td>{r['avg_dur_ms']/1000:.1f}s</td></tr>"
        for r in summary_rows
    ) + "</tbody></table>"

    sections = []
    for suite_name in sorted(suites.keys()):
        rows_html = []
        for t in suites[suite_name]:
            cells = "".join(cell(by_task.get(t.id, {}).get(m)) for m in models)
            rows_html.append(
                f"<tr><td class='taskid'><b>{t.id}</b><br><span class='desc'>{t.desc[:120]}</span></td>{cells}</tr>"
            )
        sections.append(f"""
        <h2>{suite_name} ({len(suites[suite_name])} tasks)</h2>
        <table class='grid'>
          <thead><tr><th class='taskcol'>Task</th>{head_models}</tr></thead>
          <tbody>{''.join(rows_html)}</tbody>
        </table>
        """)

    # 任务详情可展开块
    details_html = []
    for t in tasks:
        rows = []
        for m in models:
            tr = by_task.get(t.id, {}).get(m)
            if not tr:
                continue
            out = tr.get("llm_output") or {}
            err = tr.get("error")
            grader_html = "".join(
                f"<li class='{'ok' if g['passed'] else 'fail'}'><b>{g['grader']}</b>: {g['reason']}</li>"
                for g in tr.get("grader_results", [])
            )
            if err:
                body = f"<pre class='err'>{err}</pre>"
            else:
                body = (
                    f"<div><b>summary:</b> {out.get('summary','')}</div>"
                    f"<div><b>score:</b> {out.get('score')}</div>"
                    f"<div><b>nativeVersion:</b> {out.get('nativeVersion','')}</div>"
                    f"<div><b>gaps ({len(out.get('gaps') or [])}):</b><ul>"
                    + "".join(
                        f"<li>[{g.get('category','?')}] {g.get('title','')}: <code>{g.get('original','')}</code> → <code>{g.get('better','')}</code></li>"
                        for g in (out.get("gaps") or [])
                    )
                    + "</ul></div>"
                )
            rows.append(f"""
              <details class='trial'>
                <summary><b>{m}</b> · {'✓' if tr.get('passed') else '✗'} · {tr.get('duration_ms')}ms</summary>
                <ul class='graders'>{grader_html}</ul>
                {body}
              </details>
            """)
        # 题面
        sc = t.input.get("scenario") or {}
        details_html.append(f"""
        <details class='task'>
          <summary><b>{t.id}</b> — {t.desc}</summary>
          <div class='input'>
            <b>text:</b> <code>{t.input.get('text','')}</code><br>
            <b>scenario:</b> {sc.get('where','')} · {sc.get('mission','')}
          </div>
          {''.join(rows)}
        </details>
        """)

    return f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>SpeakUp 模型对比评测</title>
<style>
  body {{ font-family: -apple-system, sans-serif; padding: 20px; background: #fff; color: #1f2328; max-width: 1400px; margin: 0 auto; }}
  h1 {{ margin-top: 0; }}
  h2 {{ margin-top: 28px; border-bottom: 1px solid #e0e0e0; padding-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; }}
  th, td {{ padding: 8px 10px; border: 1px solid #e0e0e0; text-align: left; vertical-align: top; font-size: 13px; }}
  th {{ background: #f6f8fa; font-weight: 600; }}
  table.summary td, table.summary th {{ font-size: 14px; }}
  table.grid td.ok {{ background: #dcfce7; color: #14532d; }}
  table.grid td.fail {{ background: #fee2e2; color: #7f1d1d; }}
  table.grid td.na {{ color: #999; text-align: center; }}
  td.taskid {{ width: 240px; font-family: ui-monospace, monospace; }}
  td.taskid .desc {{ color: #57606a; font-size: 12px; font-weight: 400; }}
  td .reason {{ font-size: 11px; color: #7f1d1d; opacity: 0.85; }}
  details.task {{ margin: 10px 0; padding: 10px; border: 1px solid #d0d7de; border-radius: 6px; }}
  details.task > summary {{ cursor: pointer; font-size: 14px; }}
  details.trial {{ margin: 6px 0 6px 16px; padding: 8px 10px; background: #f6f8fa; border-radius: 4px; }}
  ul.graders li.ok {{ color: #14532d; }}
  ul.graders li.fail {{ color: #7f1d1d; }}
  code {{ background: #eef0f2; padding: 1px 4px; border-radius: 3px; font-size: 12px; }}
  pre.err {{ background: #fef2f2; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 12px; }}
  .input {{ background: #fffbea; padding: 8px; border-radius: 4px; margin: 8px 0; font-size: 13px; }}
</style>
</head>
<body>
<h1>SpeakUp 模型对比评测</h1>
<p>26 tasks · {len(models)} models · 1 trial · base_url=<code>{BASE_URL}</code></p>

<h2>总览</h2>
{summary_table}

<h2>每条任务对比</h2>
<p>cell 含义：<code>✓/✗ score · gaps数 · latency</code>。鼠标悬停看 summary。</p>
{''.join(sections)}

<h2>详情（点击展开）</h2>
{''.join(details_html)}

</body></html>"""


async def main():
    tasks_root = SERVER_ROOT / "evals" / "tasks"
    tasks = load_tasks(tasks_root, "all")
    print(f"loaded {len(tasks)} tasks; running × {len(MODELS)} models")

    all_results = []
    for m in MODELS:
        mr = await run_model(m, tasks)
        all_results.append(mr)

    out_json = Path("/tmp/speakup-models-compare.json")
    out_json.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    out_html = Path("/tmp/speakup-models-compare.html")
    out_html.write_text(render_html(all_results, tasks), encoding="utf-8")

    print("\n=== SUMMARY ===")
    for mr in all_results:
        passed = sum(1 for r in mr["tasks"] if r["passed"])
        total = len(mr["tasks"])
        avg_dur = sum(r["duration_ms"] for r in mr["tasks"]) / max(1, total)
        print(f"  {mr['model']:20s}  {passed}/{total}  ({100*passed/total:.0f}%)  avg {avg_dur/1000:.1f}s")

    print(f"\n📄 HTML: {out_html}")
    print(f"📦 JSON: {out_json}")


if __name__ == "__main__":
    asyncio.run(main())
