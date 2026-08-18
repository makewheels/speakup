"""评测结果回写 Langfuse：dataset run + 每 trial score + run 级 pass@k/pass^k。

和 llm_trace 同纪律：未配 LANGFUSE_* 时整体 no-op；任何异常只 warning 不抛——
回写失败绝不影响评测本身和本地报告。

数据布局（speakup dev project）：
- dataset 名 `speakup/evals/<suite>-v1`（git 的 tasks/ 目录是事实源，dataset 只是镜像）
- task → dataset item 按 input 全等匹配（item metadata 里没有 task id）
- 每个 task 选一个"代表 trial"（优先第一个失败 trial，方便点开看失败原因）
  → dataset run item（同 run 同 item 服务端只保留一条）+ task 级 score
  `pass@k` / `pass^k`（0/1，挂在代表 trial 的 trace 上；Experiments 矩阵按列平均即总通过率）
- 每个 trial → score `eval-pass`（0/1，comment 带 grader 失败理由）

注意：v4 服务端会静默丢弃"只有 dataset_run_id 没有 trace_id"的 score，
所以聚合指标一律挂 trace，不用 run 级 score。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evals.harness import TaskReport

logger = logging.getLogger(__name__)


def dataset_name(suite: str) -> str:
    return f"speakup/evals/{suite}-v1"


def default_run_name(label: str) -> str:
    """run 名 = 模型标签 + UTC 时间戳，重复跑不撞名。"""
    return f"{label} {datetime.now(timezone.utc).strftime('%m-%d %H:%M')}Z"


def _input_key(inp: Any) -> str:
    return json.dumps(inp, sort_keys=True, ensure_ascii=False)


def _grader_comment(trial: Any) -> str:
    if trial.error:
        return f"trial error: {trial.error.splitlines()[0][:200]}"
    failed = [g for g in trial.grader_results if not g["passed"]]
    if not failed:
        return "all graders passed"
    return "; ".join(f"{g['grader']}: {g['reason']}" for g in failed)[:800]


def _publish_task(client: Any, item: Any, report: Any, run_name: str,
                  run_desc: str, trials_k: int) -> bool:
    """单 task 的回写：每 trial 一条 eval-pass；代表 trial 挂 run item + pass@k/pass^k。"""
    for trial in report.trials:
        if trial.trace_id is None:
            continue
        try:
            client.create_score(
                trace_id=trial.trace_id,
                name="eval-pass",
                value=1.0 if trial.passed else 0.0,
                comment=_grader_comment(trial),
            )
        except Exception as e:
            logger.warning("langfuse 回写 eval-pass 失败（%s#%s）: %s",
                           report.task.id, trial.trial_index, e)

    rep = next((t for t in report.trials if not t.passed), report.trials[0])
    if rep.trace_id is None:
        return False
    try:
        client.api.dataset_run_items.create(
            run_name=run_name,
            run_description=run_desc,
            dataset_item_id=item.id,
            trace_id=rep.trace_id,
        )
        for name, value in (("pass@k", report.pass_at_k), ("pass^k", report.pass_pow_k)):
            client.create_score(
                trace_id=rep.trace_id,
                name=name,
                value=value,
                comment=f"{report.task.id} over {trials_k} trials",
            )
        return True
    except Exception as e:
        logger.warning("langfuse 回写 run item 失败（%s）: %s", report.task.id, e)
        return False


def publish(suite: str, run_name: str, reports: list[TaskReport], trials_k: int) -> None:
    """把一次 run_suite 的结果写进 Langfuse。未启用/写不进时安静退出。"""
    from services import llm_trace

    client = llm_trace.get_client()
    if client is None or not reports:
        return

    try:
        dataset = client.get_dataset(dataset_name(suite))
    except Exception as e:
        logger.warning("langfuse 回写跳过（dataset 拉取失败）: %s", e)
        return
    item_by_input = {_input_key(i.input): i for i in dataset.items}

    n_items = 0
    run_desc = f"speakup evals {suite} trials={trials_k}"
    for report in reports:
        item = item_by_input.get(_input_key(report.task.input))
        if item is None:
            logger.warning("langfuse 回写：task %s 无匹配 dataset item，跳过", report.task.id)
            continue
        if _publish_task(client, item, report, run_name, run_desc, trials_k):
            n_items += 1

    logger.info("langfuse 回写完成：run=%s items=%d", run_name, n_items)
