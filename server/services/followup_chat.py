"""练习反馈的追问对话：组装练习上下文，流式输出纯文本回答并写入 LLM 审计。"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from services.corrector import _get_client, _scenario_block
from services.llm_audit import (
    _safe_insert as audit_safe_insert,
    client_params,
    content_to_text,
    estimate_text_cost,
    extract_usage,
    serialize_messages,
)

logger = logging.getLogger(__name__)

FOLLOWUP_SYSTEM = """你是这位中国成年学习者的英语口语私教。他刚在一个真实场景里练了口语，你已经给过反馈，现在他想就这次练习继续追问。

像真人教练一样对话：
- 紧扣这次练习的上下文（场景、他说的话、你给的反馈）。他问"为什么这么改""还能怎么说""帮我多举几个例子""这个词什么意思""换个场合怎么说"都好好答。
- 讲解用中文，英文表达/例句用英文（可加简短中文解释）。
- 简洁、直接、给干货；别长篇大论，别堆术语。
- 多鼓励他开口，可以顺手给一两个新例句或小练习让他模仿。
- 纯自然对话：**只输出纯文本**，不要任何 markdown 语法——不要 `**加粗**`、不要 `#` 标题、不要 ``` 代码块。要分点就用「·」或直接换行。"""


def _followup_context(scenario: dict | None, attempt: dict | None) -> str:
    """把场景、原话和已给反馈拼成追问上下文。"""
    parts = [_scenario_block(scenario).strip()] if scenario else []
    if attempt:
        parts.append(f'他这次说的话："{attempt.get("transcript", "")}"')
        if attempt.get("nativeVersion"):
            parts.append(f'你给的 native 版改写："{attempt["nativeVersion"]}"')
        gaps = attempt.get("gaps") or []
        if gaps:
            lines = "\n".join(
                f'  · [{g.get("category", "")}] {g.get("original", "")} → {g.get("better", "")}（{g.get("why", "")}）'
                for g in gaps
            )
            parts.append(f"你指出的 gaps：\n{lines}")
        if attempt.get("summary"):
            parts.append(f'你的小结：{attempt["summary"]}')
    return "\n".join(p for p in parts if p)


def _build_followup_messages(
    scenario: dict | None, attempt: dict | None, history: list | None, question: str
) -> list:
    system = FOLLOWUP_SYSTEM + "\n\n本次练习的上下文：\n" + _followup_context(scenario, attempt)
    messages: list = [SystemMessage(content=system)]
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content", "")
        if not content:
            continue
        messages.append(AIMessage(content=content) if role == "assistant" else HumanMessage(content=content))
    messages.append(HumanMessage(content=question))
    return messages


async def followup_chat_stream(  # noqa: C901
    scenario: dict | None,
    attempt: dict | None,
    history: list | None,
    question: str,
    link_to: dict | None = None,
) -> AsyncGenerator[tuple[str, dict], None]:
    """流式输出追问回答，首 token 前的瞬时失败安全重试一次。"""
    if not question or not question.strip():
        yield "error", {"message": "请输入你想问的内容。"}
        return

    messages = _build_followup_messages(scenario, attempt, history, question)
    started = time.monotonic()
    full_text = ""
    final_metadata: dict | None = None
    err: str | None = None
    model = "?"
    prompt_tok = 0
    completion_tok = 0

    final_usage: dict | None = None
    try:
        for stream_attempt in range(2):
            try:
                async for chunk in _get_client().astream(messages):
                    delta = content_to_text(chunk.content)
                    if delta:
                        full_text += delta
                        yield "chunk", {"text": delta}
                    if hasattr(chunk, "response_metadata") and chunk.response_metadata:
                        final_metadata = chunk.response_metadata
                    if getattr(chunk, "usage_metadata", None):
                        final_usage = chunk.usage_metadata
                break
            except Exception:
                if stream_attempt == 0 and not full_text:
                    logger.warning("followup_chat_stream transient pre-token failure; retrying once")
                    await asyncio.sleep(0.25)
                    continue
                raise
        model, prompt_tok, completion_tok = extract_usage(final_metadata, final_usage)
        if prompt_tok or completion_tok:
            yield "usage", {"model": model, "promptTokens": prompt_tok, "completionTokens": completion_tok}
        yield "done", {"text": full_text}
    except Exception as e:
        logger.error("followup_chat_stream error: %s: %s", type(e).__name__, e)
        err = f"{type(e).__name__}: {e}"
        msg = "AI 服务超时，请重试。" if "timeout" in type(e).__name__.lower() else f"AI 服务出错（{type(e).__name__}），请重试。"
        yield "error", {"message": msg}

    duration_ms = int((time.monotonic() - started) * 1000)
    cost = estimate_text_cost(model, prompt_tok, completion_tok)
    await audit_safe_insert({
        "kind": "followup_chat",
        "model": model,
        "request": {
            "systemPrompt": messages[0].content,
            "userPrompt": question,
            "messages": serialize_messages(messages),  # 完整消息列表（含多轮历史），一字不少
            "params": client_params(_get_client()),
        },
        "response": {"raw": full_text},  # 完整响应，不截断
        "tokens": {"prompt": prompt_tok, "completion": completion_tok},
        "cost": float(f"{cost:.6f}"),
        "durationMs": duration_ms,
        "error": err,
        "linkedTo": link_to or {},
        "createdAt": datetime.now(timezone.utc),
    })
