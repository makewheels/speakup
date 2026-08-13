"""LLM 调用审计：把每次调 LLM / 生图的 prompt + response + tokens + 估算成本写进
`llmCalls` 集合，用 linkedTo 字段挂到 scenarioId / sessionId / attemptIndex / userId，
方便事后调试题目质量、反馈漏抓等问题。

用法：
    from services.llm_audit import audited_invoke, log_image_call, log_video_call

    # LLM 调用
    result = await audited_invoke(
        client, messages,
        kind="scenario_gen_public",
        link_to={"scenarioId": sid},
    )
    raw = result["raw"]
    parsed = result["parsed"]      # 如果 parser 给了，自动入库

    # 生图（不是 LangChain 客户端）
    await log_image_call(
        model="doubao-seedream-5.0-lite",
        prompt=prompt,
        size_bytes=len(image),
        link_to={"scenarioId": sid},
    )

写库失败只记日志不抛——绝不让 audit 拖垮主路径。
"""

import logging
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable

from db.connection import get_db
from services import llm_trace
from utils.data_source import normalize_source_type
from utils.id_generator import llm_call_id

logger = logging.getLogger(__name__)

# ---------- 成本估算 ----------
# 单位：元/百万 tokens（调试用估算；Agent Plan 额度内边际成本按 0 记）
TEXT_PRICING = {
    "ark-code-latest":  {"prompt": 0.0,  "completion": 0.0},
    "glm-5.2":          {"prompt": 0.0,  "completion": 0.0},
    "deepseek-v4-pro":  {"prompt": 0.0,  "completion": 0.0},
    "deepseek-v4-pro-260425": {"prompt": 0.0, "completion": 0.0},
    "qwen3.7-plus":     {"prompt": 0.4,  "completion": 1.2},
    "qwen3-max":        {"prompt": 4.0,  "completion": 12.0},
    "qwen-plus":        {"prompt": 0.4,  "completion": 1.2},
    "qwen-max":         {"prompt": 4.0,  "completion": 12.0},
    "qwen-turbo":       {"prompt": 0.3,  "completion": 0.6},
}
TEXT_PRICING_FALLBACK = {"prompt": 1.0, "completion": 3.0}

# 单位：元/张（按张计费）
IMAGE_PRICING = {
    "doubao-seedream-5.0-lite": 0.0,
    "wanx2.1-t2i-turbo": 0.14,
    "wan2.2-t2i-flash":  0.05,
    "wanx-v1":           0.30,
    "wan2.7-image":      0.30,
    "wanx2.1-t2i-plus":  0.20,
}
IMAGE_PRICING_FALLBACK = 0.30

VIDEO_PRICING = {
    "doubao-seedance-1.5-pro": 0.0,
    "doubao-seedance-2.0": 0.0,
    "doubao-seedance-2.0-fast": 0.0,
}
VIDEO_PRICING_FALLBACK = 0.0


def estimate_text_cost(model: str, prompt_tok: int, completion_tok: int) -> float:
    p = TEXT_PRICING.get(model, TEXT_PRICING_FALLBACK)
    return prompt_tok / 1_000_000 * p["prompt"] + completion_tok / 1_000_000 * p["completion"]


def estimate_image_cost(model: str) -> float:
    return IMAGE_PRICING.get(model, IMAGE_PRICING_FALLBACK)


def estimate_video_cost(model: str) -> float:
    return VIDEO_PRICING.get(model, VIDEO_PRICING_FALLBACK)


# ---------- 写库（fire-and-forget 安全包装） ----------

async def _safe_insert(doc: dict, *, _trace: bool = True) -> None:
    try:
        await get_db().llmCalls.insert_one(doc)
    except Exception as e:
        logger.warning("llmCalls 写入失败（不影响主路径）: %s", e)
    # 双写 Langfuse。audited_invoke 已用 start/finish 精确埋点的文档传 _trace=False 防重
    if _trace:
        llm_trace.log_call(doc)


# ---------- 公共 API ----------

def content_to_text(content: Any) -> str:
    """Normalize LangChain/OpenAI message content into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or json.dumps(content, ensure_ascii=False))
    return str(content)

async def audited_invoke(
    client: Any,
    messages: list,
    *,
    kind: str,
    link_to: dict | None = None,
    parser: Callable[[str], dict] | None = None,
) -> dict:
    """包装 LLM 调用：调 + 解析 + 入库。

    Args:
        client: LangChain client（必须支持 .ainvoke(messages)）
        messages: SystemMessage + HumanMessage 列表
        kind: 调用类型（scenario_gen_public / scenario_gen_custom / correct / correct_retry）
        link_to: 反查用，e.g. {"scenarioId": "...", "sessionId": "...", "userId": "..."}
        parser: 可选，对 raw response 做结构化解析；解析失败留 error 字段

    Returns:
        {"raw": str | None, "parsed": dict | None, "tokens": dict, "model": str,
         "cost": float, "durationMs": int, "error": str | None,
         "metadata": dict | None}
    """
    started = time.monotonic()
    raw: str | None = None
    metadata: dict | None = None
    error: str | None = None
    parsed: dict | None = None
    tracer = llm_trace.start(
        kind=kind,
        link_to=link_to,
        input={
            "systemPrompt": messages[0].content if messages else "",
            "userPrompt": messages[1].content if len(messages) > 1 else "",
        },
    )

    try:
        resp = await client.ainvoke(messages)
        raw = content_to_text(resp.content)
        metadata = resp.response_metadata or {}
    except Exception as e:
        error = f"llm_invoke_failed: {e}"

    if raw is not None and parser is not None:
        try:
            parsed = parser(raw)
        except Exception as e:
            error = f"parse_failed: {e}"

    duration_ms = int((time.monotonic() - started) * 1000)
    tokens = (metadata or {}).get("token_usage", {}) or {}
    model = (metadata or {}).get("model_name") or "?"
    prompt_tok = int(tokens.get("prompt_tokens") or 0)
    completion_tok = int(tokens.get("completion_tokens") or 0)
    cost = estimate_text_cost(model, prompt_tok, completion_tok)

    doc = {
        "_id": llm_call_id(),
        "kind": kind,
        "sourceType": normalize_source_type((link_to or {}).get("sourceType")),
        "model": model,
        "request": {
            "systemPrompt": messages[0].content if messages else "",
            "userPrompt": messages[1].content if len(messages) > 1 else "",
        },
        "response": {
            "raw": (raw or "")[:8000],   # cap 8K 字符防爆库
            "parsed": parsed,
        },
        "tokens": {"prompt": prompt_tok, "completion": completion_tok},
        "cost": round(cost, 6),
        "durationMs": duration_ms,
        "error": error,
        "linkedTo": link_to or {},
        "createdAt": datetime.now(timezone.utc),
    }
    llm_trace.finish(tracer, doc)
    await _safe_insert(doc, _trace=False)

    return {
        "raw": raw,
        "parsed": parsed,
        "tokens": tokens,
        "model": model,
        "cost": cost,
        "durationMs": duration_ms,
        "error": error,
        "metadata": metadata,
    }


async def log_image_call(
    *,
    model: str,
    prompt: str,
    size_bytes: int = 0,
    link_to: dict | None = None,
    error: str | None = None,
) -> None:
    """图片生成审计——不走 LLM 链路所以单独 API。"""
    cost = 0.0 if error else estimate_image_cost(model)
    doc = {
        "_id": llm_call_id(),
        "kind": "image",
        "sourceType": normalize_source_type((link_to or {}).get("sourceType")),
        "model": model,
        "request": {"prompt": (prompt or "")[:2000]},
        "response": {"sizeBytes": size_bytes},
        "tokens": {},
        "cost": round(cost, 6),
        "error": error,
        "linkedTo": link_to or {},
        "createdAt": datetime.now(timezone.utc),
    }
    await _safe_insert(doc)


async def log_video_call(
    *,
    model: str,
    prompt: str,
    metadata: dict | None = None,
    link_to: dict | None = None,
    error: str | None = None,
) -> None:
    """视频生成审计。"""
    metadata = metadata or {}
    cost = 0.0 if error else estimate_video_cost(model)
    doc = {
        "_id": llm_call_id(),
        "kind": "video",
        "sourceType": normalize_source_type((link_to or {}).get("sourceType")),
        "model": model,
        "request": {"prompt": (prompt or "")[:2000], "taskId": metadata.get("taskId", "")},
        "response": {"sizeBytes": metadata.get("sizeBytes", 0)},
        "tokens": {},
        "cost": round(cost, 6),
        "durationMs": metadata.get("durationMs", 0),
        "error": error,
        "linkedTo": link_to or {},
        "createdAt": datetime.now(timezone.utc),
    }
    await _safe_insert(doc)
