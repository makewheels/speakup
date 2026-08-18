"""SpeakUp evals CLI。

跑法：
    cd ~/workspace/learning/speakup/server
    python -m evals.run --suite regression --trials 3
    python -m evals.run --suite all --trials 1 --concurrency 4 --report /tmp/eval-report.html

输出：
- 终端：每条任务一行 pass/fail（pass@k + pass^k）+ 总览
- HTML 报告：每条任务可展开，看到所有 trial 的 LLM 原始输出 + 每个 grader 判定理由
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 让 `python -m evals.run` 在 server/ 下能找到 services/ 包
HERE = Path(__file__).parent
SERVER_ROOT = HERE.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Run SpeakUp evals against services.corrector")
    p.add_argument("--suite", default="regression",
                   help="任务子目录名 (regression / capability / all)。默认 regression")
    p.add_argument("--trials", type=int, default=3, help="每条任务跑几次（pass@k / pass^k 的 k）")
    p.add_argument("--concurrency", type=int, default=4, help="任务并发数（trial 内部并发会再 /2）")
    p.add_argument("--report", default="/tmp/speakup-evals-report.html", help="HTML 报告输出路径")
    p.add_argument("--task", default=None, help="只跑指定 task id（debug 用）")
    args = p.parse_args()

    from evals.harness import load_tasks, run_suite
    from evals.report import render_html, render_text

    tasks_root = HERE / "tasks"
    tasks = load_tasks(tasks_root, args.suite)
    if args.task:
        tasks = [t for t in tasks if t.id == args.task]
    if not tasks:
        print(f"✗ no tasks found in {tasks_root}/{args.suite}", file=sys.stderr)
        return 2

    print(f"▶ running {len(tasks)} tasks × {args.trials} trials (concurrency={args.concurrency})")
    reports = asyncio.run(run_suite(tasks, trials=args.trials, concurrency=args.concurrency))

    print(render_text(reports, k=args.trials))

    # 结果回写 Langfuse（未配 LANGFUSE_* 时 no-op）；flush 在回写后统一冲队列
    import config
    from evals import langfuse_report
    langfuse_report.publish(args.suite, langfuse_report.default_run_name(config.CHAT_MODEL),
                            reports, args.trials)

    # evals 是短进程：退出前把 langfuse trace 队列冲掉（未配 LANGFUSE_* 时 no-op）
    from services import llm_trace
    llm_trace.flush()

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_html(reports, k=args.trials), encoding="utf-8")
    print(f"\n📄 HTML report: {report_path}")

    # 退出码：任何 pass^k < 1 → 非 0（CI 友好）
    any_fail = any(r.pass_pow_k < 1.0 for r in reports)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
