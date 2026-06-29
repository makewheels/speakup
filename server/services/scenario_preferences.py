"""场景偏好匹配规则。"""

import random

LEVEL_DIFFICULTIES = {
    "beginner": {1},
    "daily": {1, 2},
    "advanced": {2, 3},
    "challenge": {3},
}

PURPOSE_FILTERS = {
    # 低压开口：寒暄和轻任务为主，避开硬核解释/观点题。
    "openup": {
        "domains": {"social", "hobby", "food", "travel", "lodging", "shopping"},
        "kinds": {"chat", "task"},
    },
    "travel": {
        "domains": {"travel", "lodging", "food", "shopping", "health", "bank", "telecom", "emergency"},
    },
    "work": {
        "domains": {"work", "job", "biz"},
    },
    "expression": {
        "kinds": {"describe", "opinion", "explain"},
    },
    "exam": {
        "kinds": {"describe", "opinion", "explain"},
    },
    "ielts": {
        "kinds": {"describe", "opinion", "explain"},
    },
    "toefl": {
        "kinds": {"describe", "opinion", "explain"},
    },
    "dailyLife": {
        "domains": {"social", "hobby", "food", "lodging", "shopping", "health", "telecom", "bank"},
        "kinds": {"chat", "task"},
    },
}


def normalized_level(level: str | None) -> str | None:
    return level if level in LEVEL_DIFFICULTIES else None


def normalized_purpose(purpose: str | None) -> str | None:
    return purpose if purpose in {*PURPOSE_FILTERS.keys(), "review"} else None


def relaxed_difficulties(level: str | None) -> set[int] | None:
    if not level:
        return None
    values = LEVEL_DIFFICULTIES[level]
    lo = max(1, min(values) - 1)
    hi = min(3, max(values) + 1)
    return set(range(lo, hi + 1))


def _scenario_domain(scenario: dict) -> str:
    return (scenario.get("category") or {}).get("domain", "")


def _matches_purpose(scenario: dict, purpose: str | None) -> bool:
    if not purpose or purpose == "review":
        return True
    f = PURPOSE_FILTERS[purpose]
    domain_ok = "domains" not in f or _scenario_domain(scenario) in f["domains"]
    kind_ok = "kinds" not in f or scenario.get("kind", "task") in f["kinds"]
    return domain_ok and kind_ok


def _matches_difficulty(scenario: dict, difficulties: set[int] | None) -> bool:
    if not difficulties:
        return True
    return scenario.get("difficulty") in difficulties


def coord_matches_difficulty(coord: dict, difficulties: set[int] | None) -> bool:
    if not difficulties:
        return True
    return coord.get("difficulty") in difficulties


def coord_matches_purpose(coord: dict, purpose: str | None) -> bool:
    if not purpose or purpose == "review":
        return True
    f = PURPOSE_FILTERS[purpose]
    domain_ok = "domains" not in f or coord.get("domainShort") in f["domains"]
    kind_ok = "kinds" not in f or coord.get("kind") in f["kinds"]
    return domain_ok and kind_ok


def _filtered(pool: list[dict], difficulties: set[int] | None, purpose: str | None) -> list[dict]:
    return [
        s for s in pool
        if _matches_difficulty(s, difficulties) and _matches_purpose(s, purpose)
    ]


def pick_public(
    public: list[dict],
    practiced: set[str],
    skipped: set[str],
    level: str | None,
    purpose: str | None,
) -> tuple[dict, str]:
    blocked = practiced | skipped
    layers = [
        [s for s in public if s["_id"] not in blocked],
        [s for s in public if s["_id"] not in practiced],
        [s for s in public if s["_id"] not in skipped],
        public,
    ]

    if level or purpose:
        strict = LEVEL_DIFFICULTIES.get(level)
        relaxed = relaxed_difficulties(level)
        filter_steps = [
            (strict, purpose, "exact"),
            (relaxed, purpose, "relaxedDifficulty"),
            (strict, None, "relaxedPurpose"),
        ]
        for base in layers:
            for difficulties, p, match in filter_steps:
                pool = _filtered(base, difficulties, p)
                if pool:
                    return random.choice(pool), match

    for base in layers:
        if base:
            return random.choice(base), "fallback"
    return random.choice(public), "fallback"


def prioritized_topup_candidates(
    candidates: list[dict],
    level: str | None,
    purpose: str | None,
) -> list[dict]:
    if not candidates or not (level or purpose):
        return candidates
    strict = LEVEL_DIFFICULTIES.get(level)
    relaxed = relaxed_difficulties(level)
    steps = [
        (strict, purpose),
        (relaxed, purpose),
        (strict, None),
    ]
    for difficulties, p in steps:
        matched = [
            c for c in candidates
            if coord_matches_difficulty(c, difficulties) and coord_matches_purpose(c, p)
        ]
        if matched:
            return matched
    return candidates
