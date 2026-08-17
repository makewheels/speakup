"""跨模型对比评测：N 个模型 × M 个任务 × K trials，终端表格 + HTML 报告 + JSON 存档。

跑法：
    cd ~/workspace/learning/speakup/server
    uv run python -m evals.compare --models glm-5.2,qwen3-max --suite regression --trials 2
    uv run python -m evals.compare --ping --models glm-5.2

模型 spec：`name[@base_url[@KEY_ENV]]`，逗号分隔。缺省 base_url / key 取
--base-url / --api-key-env（再缺省 = CHAT_BASE_URL / CHAT_API_KEY）。
KEY_ENV 是环境变量名——key 永不出现在命令行、报告和 git 里。

与 scripts/compare_models.py（已退役）的区别：
- 不再散落的 monkey-patch：client 构造/换单例收敛在 build_client + harness.use_client
- 多 trial，按 pass@k / pass^k 判（和 evals.run 同口径）
- 调用打 langfuse environment=eval + model:<label> tag
- 原始结果同时落 JSON，省去事后拼 log 的一次性脚本
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
SERVER_ROOT = HERE.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


@dataclass(frozen=True)
class ModelSpec:
    model: str
    base_url: str
    key_env: str  # 环境变量名，不是 key 本身

    @property
    def label(self) -> str:
        return self.model


def parse_specs(raw: str, default_base_url: str, default_key_env: str) -> list[ModelSpec]:
    specs = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split("@")
        if len(parts) > 3:
            raise SystemExit(f"✗ 非法模型 spec: {item!r}（期望 name[@base_url[@KEY_ENV]]）")
        model = parts[0]
        base_url = parts[1] if len(parts) > 1 and parts[1] else default_base_url
        key_env = parts[2] if len(parts) > 2 and parts[2] else default_key_env
        specs.append(ModelSpec(model=model, base_url=base_url, key_env=key_env))
    if not specs:
        raise SystemExit("✗ --models 为空")
    return specs


def build_client(spec: ModelSpec) -> Any:
    from langchain_openai import ChatOpenAI

    from services.corrector import thinking_extra_body

    key = os.environ.get(spec.key_env, "")
    if not key:
        raise SystemExit(f"✗ 环境变量 {spec.key_env} 未设置（模型 {spec.model} 需要）")
    # thinking 参数口径与 services.corrector._get_client 保持一致
    return ChatOpenAI(
        openai_api_base=spec.base_url,
        openai_api_key=key,
        model=spec.model,
        temperature=0.3,
        max_tokens=2000,
        extra_body=thinking_extra_body(spec.base_url),
        timeout=120,
    )


async def ping(spec: ModelSpec) -> tuple[str, str, str]:
    client = build_client(spec)
    started = time.monotonic()
    try:
        await client.ainvoke("reply with exactly: ok")
        return spec.model, "OK", f"{int((time.monotonic() - started) * 1000)}ms"
    except Exception as e:
        return spec.model, "ERR", str(e)[:120]


async def _ping_all(specs: list[ModelSpec]) -> list[tuple[str, str, str]]:
    return list(await asyncio.gather(*[ping(s) for s in specs]))


async def run_compare(specs: list[ModelSpec], tasks: list, trials: int,
                      concurrency: int) -> dict[str, list]:
    """模型间串行（避免限流互相干扰），模型内任务并发。"""
    from evals.harness import run_suite, use_client

    results: dict[str, list] = {}
    for spec in specs:
        print(f"\n▶ {spec.label}  ({len(tasks)} tasks × {trials} trials)")
        with use_client(build_client(spec)):
            reports = await run_suite(tasks, trials=trials, concurrency=concurrency,
                                      model_label=spec.label)
        results[spec.label] = reports
        n = len(reports)
        at_k = sum(r.pass_at_k for r in reports)
        pow_k = sum(r.pass_pow_k for r in reports)
        print(f"  → {spec.label}: pass@{trials}={int(at_k)}/{n}  pass^{trials}={int(pow_k)}/{n}")
    return results


def _avg_score(reports: list) -> float | None:
    scores = [t.llm_output.get("score") for r in reports for t in r.trials
              if t.llm_output and isinstance(t.llm_output.get("score"), (int, float))]
    return sum(scores) / len(scores) if scores else None


def _avg_duration(reports: list) -> float:
    durs = [t.duration_ms for r in reports for t in r.trials]
    return sum(durs) / len(durs) if durs else 0.0


def render_summary(results: dict[str, list], k: int) -> str:
    lines = ["", "═" * 78, f"  COMPARE SUMMARY  (k={k})", "═" * 78,
             f"  {'model':<28} {'pass@k':>10} {'pass^k':>10} {'avg score':>10} {'avg lat':>9}"]
    for label, reports in results.items():
        n = len(reports)
        at_k = sum(r.pass_at_k for r in reports)
        pow_k = sum(r.pass_pow_k for r in reports)
        score = _avg_score(reports)
        lines.append(
            f"  {label:<28} {int(at_k):>4}/{n:<5} {int(pow_k):>4}/{n:<5} "
            f"{(f'{score:.2f}' if score is not None else '?'):>10} "
            f"{_avg_duration(reports) / 1000:>8.1f}s"
        )
    lines.append("═" * 78)
    return "\n".join(lines)


def render_html(results: dict[str, list], k: int, meta: str) -> str:
    from evals.report import _HTML_HEAD

    models = list(results.keys())
    # task_id -> task 对象（取第一个模型的 reports；所有模型跑同一批任务）
    first = next(iter(results.values()))
    task_order = [r.task.id for r in first]
    task_desc = {r.task.id: r.task.desc for r in first}
    by_task: dict[str, dict[str, Any]] = {tid: {} for tid in task_order}
    for label, reports in results.items():
        for r in reports:
            by_task[r.task.id][label] = r

    def cell(label: str, tid: str) -> str:
        r = by_task[tid].get(label)
        if r is None:
            return "<td class='na'>—</td>"
        passed = sum(1 for t in r.trials if t.passed)
        total = len(r.trials)
        score = _avg_score([r])
        dur = _avg_duration([r]) / 1000
        cls = "ok" if r.pass_pow_k == 1.0 else ("flaky" if r.pass_at_k == 1.0 else "fail")
        score_s = f"{score:.1f}" if score is not None else "?"
        fails = sorted({g["grader"] for t in r.trials for g in t.grader_results if not g["passed"]})
        reason = html.escape(", ".join(fails[:3]))
        return (f"<td class='{cls}'><b>{passed}/{total}</b> · {score_s}分 · {dur:.1f}s"
                + (f"<br><span class='reason'>{reason}</span>" if fails else "") + "</td>")

    head_models = "".join(f"<th>{html.escape(m)}</th>" for m in models)
    rows = "".join(
        f"<tr><td class='taskid'><b>{html.escape(tid)}</b><br>"
        f"<span class='desc'>{html.escape(task_desc[tid][:120])}</span></td>"
        + "".join(cell(m, tid) for m in models) + "</tr>"
        for tid in task_order
    )

    summary_rows = "".join(
        f"<tr><td><b>{html.escape(label)}</b></td>"
        f"<td>{int(sum(r.pass_at_k for r in reports))}/{len(reports)}</td>"
        f"<td>{int(sum(r.pass_pow_k for r in reports))}/{len(reports)}</td>"
        f"<td>{(f'{_avg_score(reports):.2f}' if _avg_score(reports) is not None else '?')}</td>"
        f"<td>{_avg_duration(reports) / 1000:.1f}s</td></tr>"
        for label, reports in results.items()
    )

    # 每任务 × 每模型的 trial 详情
    detail_blocks = []
    for tid in task_order:
        model_blocks = []
        for label in models:
            r = by_task[tid].get(label)
            if r is None:
                continue
            trials_html = []
            for t in r.trials:
                v = "pass" if t.passed else "fail"
                graders = "".join(
                    f"<tr><td class='g-name'>{html.escape(g['grader'])}</td>"
                    f"<td class='g-verdict' style='color:{'#1a7f37' if g['passed'] else '#cf222e'};font-weight:600'>"
                    f"{'✓' if g['passed'] else '✗'}</td>"
                    f"<td class='g-reason'>{html.escape(g['reason'])}</td></tr>"
                    for g in t.grader_results
                )
                body = (f"<pre style='border-color:#cf222e;background:#ffebe9'>{html.escape(t.error)}</pre>"
                        if t.error else
                        f"<pre>{html.escape(json.dumps(t.llm_output, ensure_ascii=False, indent=2))}</pre>")
                trials_html.append(
                    f"<div class='trial'><h4>Trial #{t.trial_index} "
                    f"<span class='badge {v}'>{v.upper()}</span> "
                    f"<span style='color:#57606a;font-weight:400;font-size:12px'>({t.duration_ms} ms)</span></h4>"
                    f"{body}<table class='graders'>{graders}</table></div>"
                )
            n_passed = sum(1 for t in r.trials if t.passed)
            model_blocks.append(
                f"<details><summary><span><b>{html.escape(label)}</b></span>"
                f"<span>{n_passed}/{len(r.trials)} "
                f"<span class='badge {'pass' if r.pass_pow_k == 1.0 else ('partial' if r.pass_at_k == 1.0 else 'fail')}'>"  # noqa: E501
                f"{'PASS' if r.pass_pow_k == 1.0 else ('FLAKY' if r.pass_at_k == 1.0 else 'FAIL')}</span></span></summary>"  # noqa: E501
                f"<div class='task-body'>{''.join(trials_html)}</div></details>"
            )
        detail_blocks.append(
            f"<h3 style='text-transform:none;letter-spacing:0'>{html.escape(tid)} "
            f"<span style='color:#57606a;font-weight:400'>· {html.escape(task_desc[tid])}</span></h3>"
            + "".join(model_blocks)
        )

    extra_css = """
<style>
  table.matrix td.ok { background: #dafbe1; color: #1a7f37; }
  table.matrix td.flaky { background: #fff8c5; color: #9a6700; }
  table.matrix td.fail { background: #ffebe9; color: #cf222e; }
  table.matrix td.na { color: #999; text-align: center; }
  table.matrix th, table.matrix td { border: 1px solid #d0d7de; padding: 8px 10px;
                                     font-size: 13px; text-align: left; vertical-align: top; }
  table.matrix { border-collapse: collapse; width: 100%; }
  table.matrix th { background: #f6f8fa; }
  td.taskid { width: 220px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  td.taskid .desc { color: #57606a; font-size: 12px; font-weight: 400; }
  td .reason { font-size: 11px; opacity: 0.85; }
</style>"""

    return (
        _HTML_HEAD.replace("</head>", extra_css + "</head>")
        + f"<h1>SpeakUp 模型对比评测</h1><div class='meta'>{html.escape(meta)}</div>"
        + f"<h2>总览</h2><table class='graders' style='font-size:14px'>"
          f"<tr><td><b>model</b></td><td><b>pass@{k}</b></td><td><b>pass^{k}</b></td>"
          f"<td><b>avg score</b></td><td><b>avg latency</b></td></tr>{summary_rows}</table>"
        + f"<h2>任务 × 模型 矩阵</h2><p class='meta'>cell = 通过trial数/总trial数 · 平均分 · 平均耗时；"
          f"绿=pass^{k} 全过，黄=pass@{k} 蒙过，红=全挂。</p>"
          f"<table class='matrix'><thead><tr><th>Task</th>{head_models}</tr></thead>"
          f"<tbody>{rows}</tbody></table>"
        + "<h2>详情</h2>" + "".join(detail_blocks)
        + "</body></html>"
    )


def to_jsonable(results: dict[str, list]) -> dict:
    out = {}
    for label, reports in results.items():
        out[label] = [{
            "task_id": r.task.id,
            "suite": r.task.source_path.parent.name if r.task.source_path else "?",
            "pass_at_k": r.pass_at_k,
            "pass_pow_k": r.pass_pow_k,
            "trials": [{
                "trial_index": t.trial_index,
                "duration_ms": t.duration_ms,
                "passed": t.passed,
                "error": t.error,
                "llm_output": t.llm_output,
                "grader_results": t.grader_results,
            } for t in r.trials],
        } for r in reports]
    return out


def main() -> int:
    import config  # noqa: F401  触发 server/.env 加载

    p = argparse.ArgumentParser(description="SpeakUp 跨模型对比评测")
    p.add_argument("--models", required=True,
                   help="逗号分隔：name[@base_url[@KEY_ENV]]。例：glm-5.2,qwen3-max")
    p.add_argument("--suite", default="regression", help="regression / capability / all。默认 regression")
    p.add_argument("--trials", type=int, default=2, help="每条任务跑几次。默认 2")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--base-url", default=os.environ.get("CHAT_BASE_URL", ""),
                   help="默认 base_url（模型 spec 未带 @ 时）。默认读 CHAT_BASE_URL")
    p.add_argument("--api-key-env", default="CHAT_API_KEY",
                   help="默认 key 的环境变量名。默认 CHAT_API_KEY")
    p.add_argument("--ping", action="store_true", help="只探活，不跑评测")
    p.add_argument("--out", default=None, help="报告输出目录。默认 mktemp")
    args = p.parse_args()

    specs = parse_specs(args.models, args.base_url, args.api_key_env)

    if args.ping:
        for model, status, info in asyncio.run(_ping_all(specs)):
            print(f"[{status}] {model:28s} {info}")
        return 0

    from evals.harness import load_tasks

    tasks = load_tasks(HERE / "tasks", args.suite)
    if not tasks:
        print(f"✗ no tasks found in suite {args.suite}", file=sys.stderr)
        return 2

    print(f"▶ {len(specs)} models × {len(tasks)} tasks × {args.trials} trials")
    results = asyncio.run(run_compare(specs, tasks, args.trials, args.concurrency))

    from services import llm_trace
    llm_trace.flush()

    print(render_summary(results, k=args.trials))

    out_dir = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="speakup-compare-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = (f"models={', '.join(s.label for s in specs)} · suite={args.suite} · "
            f"trials={args.trials} · {time.strftime('%Y-%m-%d %H:%M')}")
    html_path = out_dir / "report.html"
    html_path.write_text(render_html(results, k=args.trials, meta=meta), encoding="utf-8")
    json_path = out_dir / "report.json"
    json_path.write_text(json.dumps(to_jsonable(results), ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")
    print(f"\n📄 HTML: {html_path}")
    print(f"📦 JSON: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
