"""评测 harness：跑任务 × N trials，记录原始 transcript 给 graders。

不经 mongo / FastAPI：直接调 services.corrector.correct_text，把它当 pure function 用。
（_load_practice / _save_attempt_and_review 是 route 层职责，eval 不关心。）

按 Anthropic eval 指引："每个 trial 从干净环境开始" —— 这里靠 correct_text 本身无状态保证，
唯一全局是 services.corrector._client（LangChain 客户端复用），允许且无副作用。
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Task:
    id: str
    desc: str
    input: dict[str, Any]          # {text, scenario?, prev_attempt?, round?}
    expectations: list[dict[str, Any]]
    source_path: Path | None = None


@dataclass
class TrialResult:
    """单次 LLM 调用 + 评分的完整记录。grader 报告里要展示给人看。"""
    trial_index: int
    duration_ms: int
    llm_output: dict[str, Any] | None    # corrector 的结构化返回
    error: str | None = None
    grader_results: list[dict[str, Any]] = field(default_factory=list)  # [{grader, passed, reason}]

    @property
    def passed(self) -> bool:
        """这一 trial 是否全 grader 通过。"""
        if self.error or self.llm_output is None:
            return False
        return all(g["passed"] for g in self.grader_results)


@dataclass
class TaskReport:
    task: Task
    trials: list[TrialResult]

    @property
    def pass_at_k(self) -> float:
        """k 次至少 1 次过 → 1.0，否则 0.0（一个任务 → 单一 0/1 数）。"""
        return 1.0 if any(t.passed for t in self.trials) else 0.0

    @property
    def pass_pow_k(self) -> float:
        """k 次全过 → 1.0；任何一次失败 → 0.0。"""
        if not self.trials:
            return 0.0
        return 1.0 if all(t.passed for t in self.trials) else 0.0


def load_tasks(root: Path, suite: str) -> list[Task]:
    """从 evals/tasks/<suite>/*.json 加载任务集。suite='all' 加载所有。"""
    if suite == "all":
        files = sorted(root.glob("*/*.json"))
    else:
        files = sorted((root / suite).glob("*.json"))
    tasks = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        tasks.append(Task(
            id=data["id"],
            desc=data["desc"],
            input=data["input"],
            expectations=data["expectations"],
            source_path=f,
        ))
    return tasks


async def run_one_trial(task: Task, trial_index: int) -> TrialResult:
    """跑一次 corrector，捕异常不让单条挂掉整批。"""
    from services.corrector import correct_text  # 延迟 import：让 evals 包本身不依赖 server 启动

    started = time.monotonic()
    try:
        result = await correct_text(
            text=task.input["text"],
            scenario=task.input.get("scenario"),
            prev_attempt=task.input.get("prev_attempt"),
            round=task.input.get("round", 1),
            link_to={"eval_task": task.id, "eval_trial": trial_index},
        )
        duration = int((time.monotonic() - started) * 1000)
        return TrialResult(trial_index=trial_index, duration_ms=duration, llm_output=result)
    except Exception as e:
        duration = int((time.monotonic() - started) * 1000)
        return TrialResult(
            trial_index=trial_index,
            duration_ms=duration,
            llm_output=None,
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}",
        )


def apply_graders(trial: TrialResult, task: Task) -> None:
    """对每个 trial 跑所有 grader，结果写到 trial.grader_results。

    grader 自身永远不该抛 —— 内部抛了就当成 fail + 把 traceback 当 reason，方便排查。
    """
    from evals.graders import schema as schema_g
    from evals.graders import expectation as exp_g

    # 1. 始终跑 schema 系列（所有 expectation 之前的"地基"）
    for grader_name, grader_fn in schema_g.ALL.items():
        try:
            passed, reason = grader_fn(trial.llm_output, task.input)
        except Exception as e:
            passed, reason = False, f"grader crashed: {type(e).__name__}: {e}"
        trial.grader_results.append({"grader": f"schema:{grader_name}", "passed": passed, "reason": reason})

    # 2. 再跑任务级 expectation
    for exp in task.expectations:
        kind = exp["type"]
        grader_fn = exp_g.REGISTRY.get(kind)
        if grader_fn is None:
            trial.grader_results.append({
                "grader": f"expect:{kind}",
                "passed": False,
                "reason": f"unknown expectation type: {kind}",
            })
            continue
        if kind == "schema_valid":
            # schema_valid 是早期版本的占位 —— schema:* graders 已经全跑，这里跳过
            continue
        try:
            passed, reason = grader_fn(trial.llm_output, exp)
        except Exception as e:
            passed, reason = False, f"grader crashed: {type(e).__name__}: {e}"
        trial.grader_results.append({"grader": f"expect:{kind}", "passed": passed, "reason": reason})


async def run_task(task: Task, trials: int, concurrency: int = 3) -> TaskReport:
    """同一任务跑 N 次，每次独立 trial。"""
    sem = asyncio.Semaphore(concurrency)

    async def bounded(i: int) -> TrialResult:
        async with sem:
            return await run_one_trial(task, i)

    trial_results = await asyncio.gather(*(bounded(i) for i in range(trials)))
    for tr in trial_results:
        apply_graders(tr, task)
    return TaskReport(task=task, trials=list(trial_results))


async def run_suite(tasks: list[Task], trials: int, concurrency: int) -> list[TaskReport]:
    """所有任务并发跑（受外层 concurrency 控制 task 之间并行；每个 task 内部再控 trial 并行）。"""
    # 任务级并行（小一些，避免 LLM 限流），trial 级在 run_task 内部再控
    task_sem = asyncio.Semaphore(max(1, concurrency // 2))

    async def bounded_task(t: Task) -> TaskReport:
        async with task_sem:
            return await run_task(t, trials=trials, concurrency=concurrency)

    return list(await asyncio.gather(*(bounded_task(t) for t in tasks)))
