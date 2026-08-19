"""场景题人工评测集的加载与确定性校验。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.scenario_quality import grade_scenario


DIMENSIONS = (
    "real_world_use",
    "speaking_motivation",
    "task_clarity",
    "speakability",
    "specificity",
    "novelty",
    "difficulty_fit",
    "cultural_safety",
)
BUCKETS = ("positive", "negative", "boundary")
VERDICTS = {"pass", "fail", "borderline"}
DEFAULT_DATASET_DIR = Path(__file__).parent / "scenario_tasks" / "pilot_v1"


@dataclass(frozen=True)
class DatasetSummary:
    families: int
    cases: int
    buckets: dict[str, int]
    domains: dict[str, int]
    kinds: dict[str, int]
    verdicts: dict[str, int]


def load_families(root: Path = DEFAULT_DATASET_DIR) -> list[dict[str, Any]]:
    files = sorted(root.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no scenario eval files under {root}")
    return [json.loads(path.read_text(encoding="utf-8")) for path in files]


def flatten_cases(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for family in families:
        for case in family.get("cases", []):
            records.append(
                {
                    "familyId": family.get("familyId"),
                    "coordinate": family.get("coordinate", {}),
                    **case,
                }
            )
    return records


def score_average(case: dict[str, Any]) -> float:
    scores = case.get("annotation", {}).get("scores", {})
    values = [scores[name] for name in DIMENSIONS if name in scores]
    return sum(values) / len(values) if values else 0.0


def summarize(families: list[dict[str, Any]]) -> DatasetSummary:
    records = flatten_cases(families)
    return DatasetSummary(
        families=len(families),
        cases=len(records),
        buckets=dict(Counter(item.get("bucket", "") for item in records)),
        domains=dict(Counter(item.get("coordinate", {}).get("domain", "") for item in records)),
        kinds=dict(Counter(item.get("coordinate", {}).get("kind", "") for item in records)),
        verdicts=dict(
            Counter(item.get("annotation", {}).get("verdict", "") for item in records)
        ),
    )


def _validate_family_shape(family: dict[str, Any], errors: list[str]) -> None:
    family_id = family.get("familyId") or "<missing-family-id>"
    coordinate = family.get("coordinate")
    cases = family.get("cases")
    if not isinstance(coordinate, dict):
        errors.append(f"{family_id}: coordinate must be an object")
        return
    for field in ("domain", "subId", "kind", "difficulty"):
        if coordinate.get(field) in (None, ""):
            errors.append(f"{family_id}: coordinate.{field} is required")
    if not isinstance(cases, list):
        errors.append(f"{family_id}: cases must be a list")
        return
    buckets = [case.get("bucket") for case in cases]
    if Counter(buckets) != Counter(BUCKETS):
        errors.append(f"{family_id}: want one case per bucket, got {buckets}")


def _validate_scores(case: dict[str, Any], errors: list[str]) -> None:
    case_id = case.get("id") or "<missing-case-id>"
    annotation = case.get("annotation")
    if not isinstance(annotation, dict):
        errors.append(f"{case_id}: annotation must be an object")
        return
    verdict = annotation.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"{case_id}: invalid verdict={verdict!r}")
    scores = annotation.get("scores")
    if not isinstance(scores, dict):
        errors.append(f"{case_id}: scores must be an object")
        return
    if set(scores) != set(DIMENSIONS):
        errors.append(
            f"{case_id}: score dimensions mismatch, want={list(DIMENSIONS)}, got={list(scores)}"
        )
        return
    invalid = {key: value for key, value in scores.items() if not isinstance(value, int) or not 1 <= value <= 5}
    if invalid:
        errors.append(f"{case_id}: scores must be integer 1..5, invalid={invalid}")


def validate_dataset(families: list[dict[str, Any]]) -> list[str]:  # noqa: C901
    errors: list[str] = []
    family_ids = [family.get("familyId") for family in families]
    if len(family_ids) != len(set(family_ids)):
        errors.append("familyId values must be unique")
    for family in families:
        _validate_family_shape(family, errors)

    records = flatten_cases(families)
    case_ids = [case.get("id") for case in records]
    if len(case_ids) != len(set(case_ids)):
        errors.append("case id values must be unique")
    by_id = {case.get("id"): case for case in records if case.get("id")}

    for case in records:
        case_id = case.get("id") or "<missing-case-id>"
        if case.get("bucket") not in BUCKETS:
            errors.append(f"{case_id}: invalid bucket={case.get('bucket')!r}")
        if not str(case.get("challenge", "")).strip():
            errors.append(f"{case_id}: challenge is required")
        if not str(case.get("annotation", {}).get("rationale", "")).strip():
            errors.append(f"{case_id}: annotation.rationale is required")
        _validate_scores(case, errors)

        reference_ids = case.get("referenceIds", [])
        unknown = [reference_id for reference_id in reference_ids if reference_id not in by_id]
        if unknown:
            errors.append(f"{case_id}: unknown referenceIds={unknown}")
            continue
        references = [by_id[reference_id].get("candidate", {}) for reference_id in reference_ids]
        actual_failures = sorted(
            check.name
            for check in grade_scenario(case.get("candidate", {}), references)
            if not check.passed
        )
        expected_failures = sorted(
            case.get("annotation", {}).get("expectedHardFailures", [])
        )
        if actual_failures != expected_failures:
            errors.append(
                f"{case_id}: hard failures mismatch, expected={expected_failures}, "
                f"actual={actual_failures}"
            )

        scores = case.get("annotation", {}).get("scores", {})
        if set(scores) != set(DIMENSIONS):
            continue
        average = score_average(case)
        minimum = min(scores.values())
        verdict = case.get("annotation", {}).get("verdict")
        if verdict == "pass" and (actual_failures or average < 4.0 or minimum < 3):
            errors.append(
                f"{case_id}: pass must clear hard rules, average>=4.0 and min>=3; "
                f"average={average:.2f}, min={minimum}"
            )
        if verdict == "fail" and not (actual_failures or average < 4.0 or minimum < 3):
            errors.append(f"{case_id}: fail needs a hard failure or a rubric failure")

    return errors


def validate_pilot_dataset(families: list[dict[str, Any]]) -> list[str]:
    errors = validate_dataset(families)
    summary = summarize(families)
    expected_buckets = {bucket: 8 for bucket in BUCKETS}
    if summary.families != 8:
        errors.append(f"pilot-v1: want 8 families, got {summary.families}")
    if summary.cases != 24:
        errors.append(f"pilot-v1: want 24 cases, got {summary.cases}")
    if summary.buckets != expected_buckets:
        errors.append(f"pilot-v1: want buckets={expected_buckets}, got={summary.buckets}")
    if len(summary.domains) != 8:
        errors.append(f"pilot-v1: want 8 domains, got={summary.domains}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 SpeakUp 场景题 pilot 评测集")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_DIR)
    args = parser.parse_args()
    families = load_families(args.dataset)
    errors = validate_pilot_dataset(families)
    summary = summarize(families)
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2, sort_keys=True))
    if errors:
        print("\nValidation errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("\nValidation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
