"""Langfuse trace 双写：和 `llmCalls` 集合并行的第二路观测出口。

设计约束（和 llm_audit 同纪律）：
- 不配 `LANGFUSE_SECRET_KEY` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_HOST` 时整体 no-op，本地/测试零侵入
- 任何异常只记 warning 不抛——绝不让 trace 拖垮主路径
- SDK 后台线程批量上报，主路径只承担内存队列开销

接入点只有两处（见 llm_audit.py）：
- `audited_invoke`：调用前 `start()`、拿到结果后 `finish(tracer, doc)` —— 延迟在 UI 里是准的
- `_safe_insert`：其余调用（stream / followup / image / video）由 `log_call(doc)` 统一事后登记；
  这类 span 时长≈0，真实耗时看 metadata.durationMs（SDK v4 不支持回填开始时间）

linkedTo 映射：userId/sessionId → Langfuse 一等字段；eval_task → environment="eval" + tag；
其余原样进 generation metadata，和 `llmCalls.linkedTo` 保持同一事实源。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_client: Any = None
_tried_init = False


def _get_client() -> Any | None:
    """懒加载单例。未配置 env 或 SDK 初始化失败都返回 None（= 关闭）。"""
    global _client, _tried_init
    if _tried_init:
        return _client
    _tried_init = True
    if not os.environ.get("LANGFUSE_SECRET_KEY"):
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse()  # 读 LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY / LANGFUSE_HOST
        logger.info("langfuse trace 已启用 → %s", os.environ.get("LANGFUSE_HOST", "(cloud)"))
    except Exception as e:
        logger.warning("langfuse 初始化失败，trace 关闭（不影响主路径）: %s", e)
        _client = None
    return _client


class _Tracer:
    __slots__ = ("cm", "gen")

    def __init__(self) -> None:
        self.cm: Any = None
        self.gen: Any = None


def _link_attrs(link_to: dict | None) -> tuple[dict, dict]:
    """linkedTo → (propagate_attributes 参数, 完整 linkedTo metadata)。"""
    lt = {k: str(v) for k, v in (link_to or {}).items() if v is not None}
    kw: dict[str, Any] = {}
    if lt.get("userId"):
        kw["user_id"] = lt["userId"]
    if lt.get("sessionId"):
        kw["session_id"] = lt["sessionId"]
    # eval harness 的调用打 environment=eval，和线上流量隔开
    if lt.get("eval_task"):
        kw["environment"] = "eval"
        kw["tags"] = ["eval", f"task:{lt['eval_task']}"]
        if lt.get("eval_model"):
            kw["tags"].append(f"model:{lt['eval_model']}")
    return kw, lt


def _close_cm(t: _Tracer) -> None:
    if t.cm is not None:
        try:
            t.cm.__exit__(None, None, None)
        except Exception:
            pass
        t.cm = None


def start(*, kind: str, link_to: dict | None = None, input: Any = None) -> _Tracer | None:
    """在 LLM 调用前开始一个 generation（UI 里延迟才准）。未启用返回 None。"""
    client = _get_client()
    if client is None:
        return None
    t = _Tracer()
    try:
        from langfuse import propagate_attributes

        kw, lt = _link_attrs(link_to)
        if kw:
            t.cm = propagate_attributes(**kw)
            t.cm.__enter__()
        t.gen = client.start_observation(
            name=kind,
            as_type="generation",
            input=input,
            metadata={"linkedTo": lt} if lt else None,
        )
        return t
    except Exception as e:
        logger.warning("langfuse start 失败（不影响主路径）: %s", e)
        _close_cm(t)
        return None


def _apply_doc(gen: Any, doc: dict) -> None:
    """把 llmCalls 审计文档的字段映射到 generation 上（start/finish 与 log_call 共用）。"""
    resp = doc.get("response") or {}
    tokens = doc.get("tokens") or {}
    prompt_tok = int(tokens.get("prompt") or 0)
    completion_tok = int(tokens.get("completion") or 0)
    model = doc.get("model")
    gen.update(
        model=model if model and model != "?" else None,
        output=resp.get("parsed") if resp.get("parsed") is not None else (resp.get("raw") or None),
        usage_details={"input": prompt_tok, "output": completion_tok, "total": prompt_tok + completion_tok} if (prompt_tok or completion_tok) else None,
        cost_details={"total": doc["cost"]} if doc.get("cost") else None,
        level="ERROR" if doc.get("error") else "DEFAULT",
        status_message=doc.get("error") or None,
        metadata={k: v for k, v in {
            "llmCallId": doc.get("_id"),
            "durationMs": doc.get("durationMs"),
            "linkedTo": doc.get("linkedTo") or None,
        }.items() if v is not None} or None,
    )


def finish(tracer: _Tracer | None, doc: dict) -> None:
    """结束 generation 并按审计文档回填字段。tracer 为 None（未启用）时什么都不做。"""
    if tracer is None:
        return
    try:
        if tracer.gen is not None:
            _apply_doc(tracer.gen, doc)
            tracer.gen.end()
    except Exception as e:
        logger.warning("langfuse finish 失败（不影响主路径）: %s", e)
    finally:
        _close_cm(tracer)


def log_call(doc: dict) -> None:
    """事后登记一条审计文档（stream/followup/image/video 这类完成时才落审计的调用）。

    span 起止≈同时（SDK v4 不支持回填开始时间），真实耗时在 metadata.durationMs。
    """
    kind = doc.get("kind") or "llm_call"
    req = doc.get("request") or {}
    if req.get("messages"):
        # 新格式：完整 messages + 生成参数，一字不少
        input_payload: Any = {
            "messages": req["messages"],
            "params": req.get("params") or None,
        }
    else:
        input_payload = {k: v for k, v in {
            "systemPrompt": req.get("systemPrompt"),
            "userPrompt": req.get("userPrompt") or req.get("prompt"),
        }.items() if v}
    tracer = start(
        kind=kind,
        link_to=doc.get("linkedTo"),
        input=input_payload,
    )
    finish(tracer, doc)


def flush() -> None:
    """短生命周期进程（evals CLI / 一次性脚本）退出前冲一次队列。
    长驻服务（uvicorn）靠 SDK 后台定时 flush，不用调。"""
    client = _get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as e:
        logger.warning("langfuse flush 失败: %s", e)
