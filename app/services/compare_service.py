"""Run comparison and regression detection service across 2 to 4 validation runs (Stage 14)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from app.core.status import ValidationStatus
from app.services.orchestrator_service import (
    ValidationResultDTO,
    ValidationRunSummaryDTO,
)


@dataclass(frozen=True, slots=True)
class RuleComparisonDTO:
    """Comparison item between evaluations of the same validation rule across up to 4 runs."""

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
    status_c: ValidationStatus | None = None
    status_d: ValidationStatus | None = None
    actual_c: str | None = None
    actual_d: str | None = None
    deviation_c: str | None = None
    deviation_d: str | None = None


@dataclass(frozen=True, slots=True)
class RunComparisonDTO:
    """Complete diff representation between 2 (compulsory) and up to 4 validation runs."""

    run_a: ValidationRunSummaryDTO
    run_b: ValidationRunSummaryDTO
    rule_comparisons: list[RuleComparisonDTO]
    regressions_count: int
    improvements_count: int
    unchanged_count: int
    new_rules_count: int
    removed_rules_count: int
    run_c: ValidationRunSummaryDTO | None = None
    run_d: ValidationRunSummaryDTO | None = None

    @property
    def active_runs(self) -> list[ValidationRunSummaryDTO]:
        """List of active runs participating in this comparison (2, 3, or 4)."""
        runs = [self.run_a, self.run_b]
        if self.run_c is not None:
            runs.append(self.run_c)
        if self.run_d is not None:
            runs.append(self.run_d)
        return runs


def _classify_change(
    status_a: ValidationStatus | None,
    status_b: ValidationStatus | None,
) -> str:
    if status_a is None and status_b is not None:
        return "NEW"
    if status_a is not None and status_b is None:
        return "REMOVED"
    if status_a is None and status_b is None:
        return "NEW"
    if status_a == status_b:
        return "UNCHANGED"

    # Status hierarchy for regression vs improvement:
    # PASS (good) -> WARNING (worse) -> FAIL (bad) -> ERROR (bad)
    rank: dict[ValidationStatus | None, int] = {
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
    run_c: ValidationRunSummaryDTO | None = None,
    run_d: ValidationRunSummaryDTO | None = None,
) -> RunComparisonDTO:
    """Perform side-by-side rule comparison between 2 (compulsory) and up to 4 validation runs."""
    map_a: dict[str, ValidationResultDTO] = {r.rule_name: r for r in run_a.results}
    map_b: dict[str, ValidationResultDTO] = {r.rule_name: r for r in run_b.results}
    map_c: dict[str, ValidationResultDTO] = {r.rule_name: r for r in run_c.results} if run_c else {}
    map_d: dict[str, ValidationResultDTO] = {r.rule_name: r for r in run_d.results} if run_d else {}

    all_rule_names = sorted(
        set(map_a.keys()) | set(map_b.keys()) | set(map_c.keys()) | set(map_d.keys())
    )
    comparisons: list[RuleComparisonDTO] = []

    reg_cnt = 0
    imp_cnt = 0
    unc_cnt = 0
    new_cnt = 0
    rem_cnt = 0

    for name in all_rule_names:
        item_a = map_a.get(name)
        item_b = map_b.get(name)
        item_c = map_c.get(name)
        item_d = map_d.get(name)

        st_a = item_a.status if item_a else None
        st_b = item_b.status if item_b else None
        st_c = item_c.status if item_c else None
        st_d = item_d.status if item_d else None

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

        rep_item = item_b or item_a or item_c or item_d
        target = rep_item.target_display if rep_item else ""
        val_type = rep_item.validation_type if rep_item else ""

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
                status_c=st_c,
                status_d=st_d,
                actual_c=item_c.actual_value if item_c else None,
                actual_d=item_d.actual_value if item_d else None,
                deviation_c=item_c.deviation if item_c else None,
                deviation_d=item_d.deviation if item_d else None,
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
        run_c=run_c,
        run_d=run_d,
    )


def export_comparison_to_csv(comparison: RunComparisonDTO, destination: Path | str) -> Path:
    """Export run comparison diff to a structured CSV report (supporting 2 to 4 runs)."""
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        headers = ["Change Type", "Rule Name", "Validation Type", "Target"]
        for r in comparison.active_runs:
            headers.append(f"Run #{r.id} Status")
        for r in comparison.active_runs:
            headers.append(f"Run #{r.id} Actual")
        headers.append(f"Run #{comparison.run_b.id} Deviation")

        writer.writerow(headers)

        for c in comparison.rule_comparisons:
            row = [
                c.change_type,
                c.rule_name,
                c.validation_type,
                c.target_display,
            ]
            # Statuses
            row.append(c.status_a.value if c.status_a else "-")
            row.append(c.status_b.value if c.status_b else "-")
            if comparison.run_c:
                row.append(c.status_c.value if c.status_c else "-")
            if comparison.run_d:
                row.append(c.status_d.value if c.status_d else "-")

            # Actuals
            row.append(c.actual_a or "-")
            row.append(c.actual_b or "-")
            if comparison.run_c:
                row.append(c.actual_c or "-")
            if comparison.run_d:
                row.append(c.actual_d or "-")

            # Deviation (Target Run B)
            row.append(c.deviation_b or "-")

            writer.writerow(row)
    return dest
