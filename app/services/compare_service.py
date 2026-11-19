"""Run comparison and regression detection service between two validation runs (Stage 14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.status import ValidationStatus
from app.services.orchestrator_service import (
    ValidationResultDTO,
    ValidationRunSummaryDTO,
)


@dataclass(frozen=True, slots=True)
class RuleComparisonDTO:
    """Comparison item between two evaluations of the same validation rule."""

    rule_name: str
    target_display: str
    validation_type: str
    status_a: ValidationStatus | None
    status_b: ValidationStatus | None
    actual_a: str | None
    actual_b: str | None
    deviation_a: str | None
    deviation_b: str | None
    change_type: str  # "REGRESSION", "IMPROVEMENT", "UNCHANGED", "NEW", "REMOVED"


@dataclass(frozen=True, slots=True)
class RunComparisonDTO:
    """Complete diff representation between two validation execution runs."""

    run_a: ValidationRunSummaryDTO
    run_b: ValidationRunSummaryDTO
    rule_comparisons: list[RuleComparisonDTO]
    regressions_count: int
    improvements_count: int
    unchanged_count: int
    new_rules_count: int
    removed_rules_count: int


def _classify_change(
    status_a: ValidationStatus | None,
    status_b: ValidationStatus | None,
) -> str:
    if status_a is None and status_b is not None:
        return "NEW"
    if status_a is not None and status_b is None:
        return "REMOVED"
    if status_a == status_b:
        return "UNCHANGED"

    # Status hierarchy for regression vs improvement:
    # PASS (good) -> WARNING (worse) -> FAIL (bad) -> ERROR (bad)
    rank = {
        ValidationStatus.PASS: 1,
        ValidationStatus.WARNING: 2,
        ValidationStatus.FAIL: 3,
        ValidationStatus.ERROR: 4,
    }
    r_a = rank.get(status_a, 2)
    r_b = rank.get(status_b, 2)

    if r_b > r_a:
        return "REGRESSION"
    return "IMPROVEMENT"


def compare_validation_runs(
    run_a: ValidationRunSummaryDTO,
    run_b: ValidationRunSummaryDTO,
) -> RunComparisonDTO:
    """Perform side-by-side rule comparison between Baseline Run A and Target Run B."""
    map_a: dict[str, ValidationResultDTO] = {r.rule_name: r for r in run_a.results}
    map_b: dict[str, ValidationResultDTO] = {r.rule_name: r for r in run_b.results}

    all_rule_names = sorted(set(map_a.keys()) | set(map_b.keys()))
    comparisons: list[RuleComparisonDTO] = []

    reg_cnt = 0
    imp_cnt = 0
    unc_cnt = 0
    new_cnt = 0
    rem_cnt = 0

    for name in all_rule_names:
        item_a = map_a.get(name)
        item_b = map_b.get(name)

        st_a = item_a.status if item_a else None
        st_b = item_b.status if item_b else None

        change = _classify_change(st_a, st_b)
        if change == "REGRESSION":
            reg_cnt += 1
        elif change == "IMPROVEMENT":
            imp_cnt += 1
        elif change == "NEW":
            new_cnt += 1
        elif change == "REMOVED":
            rem_cnt += 1
        else:
            unc_cnt += 1

        target = (item_b or item_a).target_display
        val_type = (item_b or item_a).validation_type

        comparisons.append(
            RuleComparisonDTO(
                rule_name=name,
                target_display=target,
                validation_type=val_type,
                status_a=st_a,
                status_b=st_b,
                actual_a=item_a.actual_value if item_a else None,
                actual_b=item_b.actual_value if item_b else None,
                deviation_a=item_a.deviation if item_a else None,
                deviation_b=item_b.deviation if item_b else None,
                change_type=change,
            )
        )

    # Sort so regressions and improvements are at top
    order = {"REGRESSION": 0, "IMPROVEMENT": 1, "NEW": 2, "REMOVED": 3, "UNCHANGED": 4}
    comparisons.sort(key=lambda c: (order.get(c.change_type, 5), c.rule_name))

    return RunComparisonDTO(
        run_a=run_a,
        run_b=run_b,
        rule_comparisons=comparisons,
        regressions_count=reg_cnt,
        improvements_count=imp_cnt,
        unchanged_count=unc_cnt,
        new_rules_count=new_cnt,
        removed_rules_count=rem_cnt,
    )
