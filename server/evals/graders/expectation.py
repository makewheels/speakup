"""任务级 expectation graders —— 任务文件里 `expectations: [{type, ...}]` 列哪些就跑哪些。

跟 schema graders 的区别：schema 是"格式无论如何都该对"，expectation 是"这条任务期望模型做到 X"。
expectation 的 spec 字典自己带参数，比如 `{"type": "score_at_least", "value": 6.5}`。
"""

from __future__ import annotations

from typing import Any


def _no_output(out: Any) -> tuple[bool, str] | None:
    if out is None:
        return False, "no LLM output"
    return None


def gaps_count_eq(out: dict | None, spec: dict) -> tuple[bool, str]:
    """gaps 数量正好 == value。常见 value=0（应当无错）/ ==1（已知就 1 个错）。"""
    if (f := _no_output(out)) is not None: return f
    n = len(out.get("gaps") or [])
    want = spec["value"]
    return (n == want, f"gaps count={n}, want={want}")


def gaps_count_at_most(out: dict | None, spec: dict) -> tuple[bool, str]:
    """gaps ≤ value。用来防"硬凑错误"。"""
    if (f := _no_output(out)) is not None: return f
    n = len(out.get("gaps") or [])
    want = spec["value"]
    return (n <= want, f"gaps count={n}, max={want}")


def no_task_gap(out: dict | None, _spec: dict) -> tuple[bool, str]:
    """任务办成了 → 不应该有 category=task 的 gap。"""
    if (f := _no_output(out)) is not None: return f
    tasks = [g for g in (out.get("gaps") or []) if g.get("category") == "task"]
    return (not tasks, f"task gaps={len(tasks)}: {[g.get('title') for g in tasks]}")


def first_gap_category_in(out: dict | None, spec: dict) -> tuple[bool, str]:
    """第一个 gap 的 category 必须 ∈ {value}（list）。

    任务跑题的 prompt 写死要求把 task gap 排最前——这条用来防回归。
    """
    if (f := _no_output(out)) is not None: return f
    gaps = out.get("gaps") or []
    if not gaps:
        return False, "no gaps at all"
    cat = gaps[0].get("category")
    allowed = set(spec["value"])
    return (cat in allowed, f"first gap category={cat!r}, allowed={allowed}")


def must_have_category(out: dict | None, spec: dict) -> tuple[bool, str]:
    """至少一条 gap 的 category ∈ 接受集合。

    value 既支持单字符串（旧用法）也支持 list（"任一个就行"，松一点，避免 task vs grammar
    vs vocabulary 这种合理的 LLM 判别歧义把 eval 噪音化）。
    """
    if (f := _no_output(out)) is not None: return f
    want = spec["value"]
    accepted = set(want) if isinstance(want, list) else {want}
    cats = [g.get("category") for g in (out.get("gaps") or [])]
    hit = accepted.intersection(cats)
    return (bool(hit), f"want category∈{accepted}, got cats={cats}")


def gap_keyword_match(out: dict | None, spec: dict) -> tuple[bool, str]:
    """至少一条 gap 的 better/original/why 拼起来包含 spec.value 里所有关键词。

    {"type": "gap_keyword_match", "value": ["went"]}  → 任意 gap 提到 went 都行（小写比较）
    防"挑错挑得很离谱"——比如学生说 "I go to school yesterday"，期望 better 含 "went"。
    """
    if (f := _no_output(out)) is not None: return f
    needles = [k.lower() for k in spec["value"]]
    gaps = out.get("gaps") or []
    for g in gaps:
        blob = " ".join([g.get("better", ""), g.get("original", ""), g.get("why", "")]).lower()
        if all(n in blob for n in needles):
            return True, f"matched gap: better={g.get('better')!r}"
    return False, f"no gap contains all of {needles}; gaps better={[g.get('better') for g in gaps]}"


def score_at_least(out: dict | None, spec: dict) -> tuple[bool, str]:
    if (f := _no_output(out)) is not None: return f
    sc = out.get("score")
    want = spec["value"]
    if sc is None:
        return False, f"score is None, want >= {want}"
    return (sc >= want, f"score={sc}, want >= {want}")


def score_at_most(out: dict | None, spec: dict) -> tuple[bool, str]:
    if (f := _no_output(out)) is not None: return f
    sc = out.get("score")
    want = spec["value"]
    if sc is None:
        return False, f"score is None, want <= {want}"
    return (sc <= want, f"score={sc}, want <= {want}")


def progress_verdict(out: dict | None, spec: dict) -> tuple[bool, str]:
    """重说轮的 progress.verdict == value（passed / improved / stuck）。"""
    if (f := _no_output(out)) is not None: return f
    progress = out.get("progress")
    if not progress:
        return False, f"no progress, want verdict={spec['value']}"
    got = progress.get("verdict")
    return (got == spec["value"], f"verdict={got!r}, want={spec['value']!r}")


def progress_verdict_in(out: dict | None, spec: dict) -> tuple[bool, str]:
    """progress.verdict ∈ value（list）—— 给 LLM 留一点余地（improved/stuck 边界本来就模糊）。"""
    if (f := _no_output(out)) is not None: return f
    progress = out.get("progress")
    if not progress:
        return False, f"no progress, want verdict∈{spec['value']}"
    got = progress.get("verdict")
    accepted = set(spec["value"])
    return (got in accepted, f"verdict={got!r}, want∈{accepted}")


def summary_contains_any(out: dict | None, spec: dict) -> tuple[bool, str]:
    """summary 必须出现 value 里至少一个关键词。用来盯"短输入要走 fast-path 给提示"。"""
    if (f := _no_output(out)) is not None: return f
    s = out.get("summary", "") or ""
    needles = spec["value"]
    found = [n for n in needles if n in s]
    return (bool(found), f"summary={s!r}, matched={found}, want any of {needles}")


def native_version_empty(out: dict | None, _spec: dict) -> tuple[bool, str]:
    """期望 nativeVersion 为空（fast-path / 短输入场景）。"""
    if (f := _no_output(out)) is not None: return f
    nv = (out.get("nativeVersion") or "").strip()
    return (nv == "", f"nativeVersion={nv!r}, want empty")


REGISTRY = {
    "schema_valid": lambda *_: (True, "see schema:* graders"),
    "gaps_count_eq": gaps_count_eq,
    "gaps_count_at_most": gaps_count_at_most,
    "no_task_gap": no_task_gap,
    "first_gap_category_in": first_gap_category_in,
    "must_have_category": must_have_category,
    "gap_keyword_match": gap_keyword_match,
    "score_at_least": score_at_least,
    "score_at_most": score_at_most,
    "progress_verdict": progress_verdict,
    "progress_verdict_in": progress_verdict_in,
    "summary_contains_any": summary_contains_any,
    "native_version_empty": native_version_empty,
}
