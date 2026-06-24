"""文本 + HTML 报告渲染。白底浅色主题（按用户全局偏好）。"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evals.harness import TaskReport


def render_text(reports: list["TaskReport"], k: int) -> str:
    """终端总览。每个任务一行 + 汇总。"""
    lines = ["", "─" * 78, f"  RESULTS  (k={k})", "─" * 78]
    sum_at_k = 0
    sum_pow_k = 0
    for r in reports:
        a = r.pass_at_k
        p = r.pass_pow_k
        sum_at_k += a
        sum_pow_k += p
        emoji = "✓" if p == 1.0 else ("△" if a == 1.0 else "✗")
        fail_summary = ""
        if p < 1.0:
            failed_graders = sorted({
                g["grader"] for t in r.trials for g in t.grader_results if not g["passed"]
            })
            if failed_graders:
                fail_summary = f"   fail: {', '.join(failed_graders[:4])}" + (
                    f" (+{len(failed_graders) - 4})" if len(failed_graders) > 4 else ""
                )
            elif any(t.error for t in r.trials):
                fail_summary = "   fail: crashed"
        lines.append(f"  {emoji} {r.task.id:<36} pass@{k}={int(a)}  pass^{k}={int(p)}{fail_summary}")
    n = len(reports)
    lines += [
        "─" * 78,
        f"  TOTAL  pass@{k}={sum_at_k}/{n} ({sum_at_k / n * 100:.0f}%)   "
        f"pass^{k}={sum_pow_k}/{n} ({sum_pow_k / n * 100:.0f}%)",
        "─" * 78,
    ]
    return "\n".join(lines)


_HTML_HEAD = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>SpeakUp Evals Report</title>
<style>
  :root { color-scheme: light; }
  body { font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 1100px; margin: 24px auto; padding: 0 20px; color: #1f2328;
         background: #ffffff; line-height: 1.45; }
  h1 { font-size: 22px; margin: 0 0 8px; }
  .meta { color: #57606a; font-size: 13px; margin-bottom: 18px; }
  .summary { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px;
             padding: 12px 16px; margin-bottom: 20px; }
  .summary b { color: #0a3069; }
  details { border: 1px solid #d0d7de; border-radius: 6px; margin: 8px 0;
            background: #ffffff; }
  details > summary { padding: 10px 14px; cursor: pointer; font-weight: 500;
                      list-style: none; display: flex; justify-content: space-between;
                      align-items: center; gap: 12px; }
  details > summary::-webkit-details-marker { display: none; }
  details[open] > summary { border-bottom: 1px solid #d0d7de; }
  .badge { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
           padding: 2px 8px; border-radius: 10px; }
  .pass { background: #dafbe1; color: #1a7f37; }
  .partial { background: #fff8c5; color: #9a6700; }
  .fail { background: #ffebe9; color: #cf222e; }
  .task-body { padding: 0 14px 14px; }
  h3 { font-size: 14px; margin: 14px 0 4px; color: #57606a; text-transform: uppercase;
       letter-spacing: 0.04em; }
  pre { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 4px;
        padding: 10px; font-size: 12px; overflow-x: auto;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        white-space: pre-wrap; word-break: break-word; }
  table.graders { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 12px; }
  table.graders td { padding: 5px 8px; border-top: 1px solid #eaeef2; vertical-align: top; }
  table.graders td.g-name { width: 220px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                            color: #1f2328; }
  table.graders td.g-verdict { width: 60px; }
  table.graders td.g-reason { color: #57606a; word-break: break-word; }
  .trial { border-top: 1px dashed #d0d7de; padding: 10px 0; }
  .trial:first-child { border-top: none; padding-top: 4px; }
  .trial h4 { font-size: 13px; margin: 0 0 4px; color: #1f2328; }
  .input-block { background: #f6f8fa; padding: 8px 12px; border-radius: 4px; margin-bottom: 8px;
                 font-size: 13px; }
  .input-block b { color: #0a3069; }
</style>
</head><body>"""


def _verdict_badge(at_k: float, pow_k: float) -> str:
    if pow_k == 1.0:
        return '<span class="badge pass">PASS</span>'
    if at_k == 1.0:
        return '<span class="badge partial">FLAKY</span>'
    return '<span class="badge fail">FAIL</span>'


def render_html(reports: list["TaskReport"], k: int) -> str:
    parts = [_HTML_HEAD]
    n = len(reports)
    sum_at_k = sum(r.pass_at_k for r in reports)
    sum_pow_k = sum(r.pass_pow_k for r in reports)

    parts.append(f"<h1>SpeakUp Evals Report</h1>")
    parts.append(f'<div class="meta">trials per task = {k} · total tasks = {n}</div>')
    parts.append(
        f'<div class="summary">'
        f'<b>pass@{k}</b>: {int(sum_at_k)}/{n} ({sum_at_k / n * 100:.0f}%) · '
        f'<b>pass^{k}</b>: {int(sum_pow_k)}/{n} ({sum_pow_k / n * 100:.0f}%)'
        f"</div>"
    )

    for r in reports:
        badge = _verdict_badge(r.pass_at_k, r.pass_pow_k)
        n_passed = sum(1 for t in r.trials if t.passed)
        parts.append("<details>")
        parts.append(
            f"<summary><span><b>{html.escape(r.task.id)}</b> · "
            f"<span style='color:#57606a;font-weight:400'>{html.escape(r.task.desc)}</span></span>"
            f"<span>{n_passed}/{len(r.trials)} {badge}</span></summary>"
        )
        parts.append('<div class="task-body">')

        # Input block
        scenario = r.task.input.get("scenario") or {}
        parts.append('<div class="input-block">')
        parts.append(f"<b>text</b>: {html.escape(r.task.input.get('text', ''))}<br>")
        if scenario:
            parts.append(
                f"<b>scenario</b>: where={html.escape(scenario.get('where', ''))} · "
                f"mission={html.escape(scenario.get('mission', ''))}"
            )
        if r.task.input.get("round", 1) > 1:
            parts.append(f"<br><b>round</b>: {r.task.input['round']}")
        parts.append("</div>")

        # Expectations
        parts.append("<h3>Expectations</h3><pre>" +
                     html.escape(json.dumps(r.task.expectations, ensure_ascii=False, indent=2)) +
                     "</pre>")

        # Trials
        parts.append("<h3>Trials</h3>")
        for t in r.trials:
            v = "PASS" if t.passed else "FAIL"
            badge_class = "pass" if t.passed else "fail"
            parts.append(f'<div class="trial">')
            parts.append(
                f'<h4>Trial #{t.trial_index} '
                f'<span class="badge {badge_class}">{v}</span> '
                f'<span style="color:#57606a;font-weight:400;font-size:12px">'
                f"({t.duration_ms} ms)</span></h4>"
            )

            if t.error:
                parts.append("<pre style='border-color:#cf222e;background:#ffebe9'>" +
                             html.escape(t.error) + "</pre>")

            if t.llm_output is not None:
                parts.append("<pre>" +
                             html.escape(json.dumps(t.llm_output, ensure_ascii=False, indent=2)) +
                             "</pre>")

            # Graders table
            parts.append('<table class="graders">')
            for g in t.grader_results:
                ok = g["passed"]
                tick = "✓" if ok else "✗"
                color = "#1a7f37" if ok else "#cf222e"
                parts.append(
                    f'<tr><td class="g-name">{html.escape(g["grader"])}</td>'
                    f'<td class="g-verdict" style="color:{color};font-weight:600">{tick}</td>'
                    f'<td class="g-reason">{html.escape(g["reason"])}</td></tr>'
                )
            parts.append("</table>")
            parts.append("</div>")

        parts.append("</div></details>")

    parts.append("</body></html>")
    return "".join(parts)
