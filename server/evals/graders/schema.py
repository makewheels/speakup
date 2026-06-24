"""Schema/格式层 graders —— 对每个 trial 都跑。

这一层是确定性、零额外 LLM 调用、cheap & fast：catch 任何 prompt 改动让结构跑偏的回归。

每个 grader 是 `(output, task_input) -> (passed, reason)`。output 可能是 None（LLM 调用本身就崩了）。
"""

from __future__ import annotations

import re
from typing import Any

# corrector 用的类别枚举（跟 SYSTEM_PROMPT 一致）
ALLOWED_CATEGORIES = {"task", "grammar", "naturalness", "vocabulary", "register"}
ALLOWED_VERDICTS = {"passed", "improved", "stuck"}
REQUIRED_FIELDS = {"summary", "nativeVersion", "gaps"}

# 中文字符（粗略检测，含中日韩统一表意，够用）
_CHINESE_RE = re.compile(r"[一-鿿]")


def _has_chinese(s: str) -> bool:
    return bool(_CHINESE_RE.search(s or ""))


def _no_llm_output(out: Any) -> tuple[bool, str] | None:
    """统一前置：output 缺失 → 整层 grader fail 给同一原因。返回 None 表示 output 可用、继续判。"""
    if out is None:
        return False, "LLM output missing (corrector failed to return)"
    return None


def output_present(out: dict | None, _input: dict) -> tuple[bool, str]:
    if out is None:
        return False, "no output"
    return True, "output present"


def required_fields(out: dict | None, _input: dict) -> tuple[bool, str]:
    if (fail := _no_llm_output(out)) is not None:
        return fail
    missing = REQUIRED_FIELDS - set(out.keys())
    if missing:
        return False, f"missing fields: {sorted(missing)}"
    return True, "all required fields present"


def summary_constraints(out: dict | None, _input: dict) -> tuple[bool, str]:
    """summary：中文、非空、≤25 字（按字符数，emoji 也算 1）。

    注：短输入（<3 words）会走 fast-path 给英文 hint（不带中文）—— 这里允许英文兜底。
    """
    if (fail := _no_llm_output(out)) is not None:
        return fail
    s = out.get("summary", "")
    if not s.strip():
        return False, "summary is empty"
    # fast-path 英文兜底（"Try saying more..." / "AI service error..."）— 跳过中文检查
    if not _has_chinese(s):
        ok = any(x in s for x in ("Try saying more", "AI service", "Evaluation failed"))
        if ok:
            return True, f"english fallback OK: {s!r}"
        return False, f"summary has no Chinese & not a known fallback: {s!r}"
    if len(s) > 30:  # 给 prompt 写的 25 字 +5 字宽容（LLM 总会超一点）
        return False, f"summary too long ({len(s)} chars > 30): {s!r}"
    return True, f"summary OK ({len(s)} chars)"


def gaps_schema(out: dict | None, _input: dict) -> tuple[bool, str]:
    """gaps 是 list；每条 gap 必须有 better/category/title/why。"""
    if (fail := _no_llm_output(out)) is not None:
        return fail
    gaps = out.get("gaps")
    if not isinstance(gaps, list):
        return False, f"gaps is not a list: {type(gaps).__name__}"
    for i, g in enumerate(gaps):
        if not isinstance(g, dict):
            return False, f"gaps[{i}] is not a dict"
        if not g.get("better", "").strip():
            return False, f"gaps[{i}].better is empty"
        if g.get("category") not in ALLOWED_CATEGORIES:
            return False, f"gaps[{i}].category invalid: {g.get('category')!r} (allowed: {ALLOWED_CATEGORIES})"
    return True, f"gaps schema OK ({len(gaps)} items)"


def gap_why_in_chinese(out: dict | None, _input: dict) -> tuple[bool, str]:
    """每条 gap.why 必须含中文（prompt 硬约束）。"""
    if (fail := _no_llm_output(out)) is not None:
        return fail
    for i, g in enumerate(out.get("gaps", [])):
        why = g.get("why", "")
        if why and not _has_chinese(why):
            return False, f"gaps[{i}].why has no Chinese: {why!r}"
    return True, "all gap.why have Chinese"


def better_in_native_version(out: dict | None, _input: dict) -> tuple[bool, str]:
    """硬约束：每条 gap.better 必须**逐字**出现在 nativeVersion 里。

    这是 prompt 里写明的硬规则——回归最容易在这里发现 LLM 没按约束走。
    """
    if (fail := _no_llm_output(out)) is not None:
        return fail
    nv = out.get("nativeVersion", "") or ""
    if not nv:
        # nativeVersion 空且 gaps 也空 → OK（短输入 fast-path）
        if not out.get("gaps"):
            return True, "nativeVersion empty + no gaps (fast-path OK)"
        return False, "nativeVersion is empty but gaps exist"
    missing = []
    for i, g in enumerate(out.get("gaps", [])):
        better = (g.get("better") or "").strip()
        if better and better not in nv:
            missing.append(f"gaps[{i}].better={better!r}")
    if missing:
        return False, f"better not in nativeVersion: {missing} | nv={nv!r}"
    return True, "all gap.better appear verbatim in nativeVersion"


def score_valid(out: dict | None, _input: dict) -> tuple[bool, str]:
    """score 要么 None，要么 0-9 之间，要么 0.5 步进。"""
    if (fail := _no_llm_output(out)) is not None:
        return fail
    sc = out.get("score")
    if sc is None:
        return True, "score is None (allowed)"
    if not isinstance(sc, (int, float)):
        return False, f"score not numeric: {sc!r}"
    if not (0 <= sc <= 9):
        return False, f"score out of [0,9]: {sc}"
    # 0.5 步进：×2 后应当是整数
    if abs((sc * 2) - round(sc * 2)) > 1e-6:
        return False, f"score not in 0.5 step: {sc}"
    return True, f"score OK: {sc}"


def progress_verdict_valid(out: dict | None, task_input: dict) -> tuple[bool, str]:
    """重说轮（round>1）必须返回 progress；非重说轮 progress 可缺。"""
    if (fail := _no_llm_output(out)) is not None:
        return fail
    is_retry = task_input.get("round", 1) > 1
    progress = out.get("progress")
    if not is_retry:
        # 非重说：progress 可有可无，有的话 verdict 仍要合法
        if progress is None:
            return True, "no progress (round=1, allowed)"
    else:
        if progress is None:
            return False, "round>1 but no progress field"
    if progress is not None:
        v = progress.get("verdict")
        if v not in ALLOWED_VERDICTS:
            return False, f"progress.verdict invalid: {v!r}"
    return True, "progress OK"


# 按顺序跑：先检 output 存在，再检字段，再检细节。
# 名字会出现在报告里，要短可读。
ALL = {
    "output_present": output_present,
    "required_fields": required_fields,
    "summary": summary_constraints,
    "gaps_schema": gaps_schema,
    "gap_why_chinese": gap_why_in_chinese,
    "better_in_native": better_in_native_version,
    "score_valid": score_valid,
    "progress_valid": progress_verdict_valid,
}
