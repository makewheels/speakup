"""场景题确定性评测：不调 LLM，先把结构、可说性和近重复这些硬底线卡住。

开放性的“有趣、真实、难度合适”由独立 LLM judge + 人工校准处理，
见 docs/scenario-evaluation.md。

规则按 interactionType 分流：standard 题完全沿用既有规则；渐进式试点题按
task/非 task 的 points-hints 契约替换 points 规则（规格见
docs/requirements/20260826-渐进式场景提示.md）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from services.interaction_types import PROGRESSIVE_HINTS, normalize_interaction_type

KINDS = {"task", "chat", "describe", "opinion", "explain"}

EXAM_SMELL = re.compile(
    r"考官|考场|口语考试|语言考试|分别从.{0,12}阐述|讨论.{0,12}利弊|"
    r"介绍.{0,8}三个|列举.{0,8}三个"
)
ABSTRACT_POINT = re.compile(
    r"假装|摇头|深呼吸|语气.{0,6}(礼貌|坚定)|表达诚意|"
    r"指出.{0,8}不合理|说明情况|进行沟通"
)
# 渐进提示除 abstract point 外，还不许出现“展开讨论”这类无法直接帮助开口的空泛指令
HINT_SMELL = re.compile(ABSTRACT_POINT.pattern + r"|展开.{0,4}讨论")
EMOJI = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF]"
)
ENGLISH_LETTER = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    reason: str


def _normalized(value: object) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", str(value or "").lower())


def scenario_similarity(left: dict, right: dict) -> float:
    keys = ("title", "story", "mission")
    a = _normalized(" ".join(str(left.get(key, "")) for key in keys))
    b = _normalized(" ".join(str(right.get(key, "")) for key in keys))
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _clean_strs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and v.strip()]


def _progressive_checks(candidate: dict) -> list[Check]:
    """渐进式试点题契约（规格第 6.1 / 10.4 节）。

    task：2-3 条必要 points + 数量一致的 2-3 条中文 hints；
    其他 kind：points 必须为空，2-3 条中文 hints 只作展开支架。
    """
    kind = candidate.get("kind")
    points = candidate.get("points")
    hints = candidate.get("hints")
    clean_points = _clean_strs(points)
    clean_hints = _clean_strs(hints)
    is_task = kind == "task"
    points_ok = (
        2 <= len(clean_points) <= 3 if is_task
        else isinstance(points, list) and not clean_points
    )
    return [
        Check("known_kind", kind in KINDS, f"kind={kind!r}"),
        Check("progressive_points", points_ok, f"kind={kind!r}, points={points!r}"),
        Check("progressive_hints", 2 <= len(clean_hints) <= 3, f"hints={hints!r}"),
        Check(
            "points_hints_aligned",
            not is_task or len(clean_points) == len(clean_hints),
            f"points={len(clean_points)}, hints={len(clean_hints)}",
        ),
        Check(
            "hints_chinese_only",
            all(not ENGLISH_LETTER.search(h) for h in clean_hints),
            f"hints={hints!r}",
        ),
        Check(
            "speakable_hints",
            not any(HINT_SMELL.search(h) for h in clean_hints),
            f"hints={hints!r}",
        ),
    ]


def grade_scenario(candidate: dict, references: list[dict] | None = None) -> list[Check]:
    references = references or []
    required = ("title", "where", "story", "mission")
    missing = [key for key in required if not str(candidate.get(key, "")).strip()]
    points = candidate.get("points")
    title = str(candidate.get("title", ""))
    where = str(candidate.get("where", ""))
    story = str(candidate.get("story", ""))
    mission = str(candidate.get("mission", ""))
    text = story + mission

    similarities = [scenario_similarity(candidate, item) for item in references]
    max_similarity = max(similarities, default=0.0)
    duplicate_title = any(
        _normalized(title) and _normalized(title) == _normalized(item.get("title"))
        for item in references
    )

    progressive = normalize_interaction_type(candidate.get("interactionType")) == PROGRESSIVE_HINTS

    checks = [Check("required_fields", not missing, f"missing={missing}")]
    if progressive:
        checks.extend(_progressive_checks(candidate))
    else:
        checks.append(Check(
            "exactly_two_points",
            isinstance(points, list) and len(points) == 2 and all(str(p).strip() for p in points),
            f"points={points!r}",
        ))
    checks.extend([
        Check("story_length", 15 <= len(story) <= 70, f"chars={len(story)}, want=15..70"),
        Check("mission_length", 6 <= len(mission) <= 30, f"chars={len(mission)}, want=6..30"),
        Check("no_exam_smell", not EXAM_SMELL.search(text), f"text={text!r}"),
    ])
    if not progressive:
        checks.append(Check(
            "speakable_points",
            isinstance(points, list) and not any(ABSTRACT_POINT.search(str(p)) for p in points),
            f"points={points!r}",
        ))
    checks.extend([
        Check("no_emoji_in_label", not EMOJI.search(title + where), f"title={title!r}, where={where!r}"),
        Check(
            "not_near_duplicate",
            not duplicate_title and max_similarity < 0.78,
            f"duplicate_title={duplicate_title}, max_similarity={max_similarity:.3f}",
        ),
    ])
    return checks


def hard_pass(candidate: dict, references: list[dict] | None = None) -> bool:
    return all(check.passed for check in grade_scenario(candidate, references))
