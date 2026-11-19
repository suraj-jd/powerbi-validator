"""Statistical computations and numeric comparison utilities for the validation engine (Stage 11)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import statistics
from typing import Sequence


@dataclass(frozen=True, slots=True)
class StatisticalSummary:
    """Summary metrics computed from a historical observation sample."""

    sample_count: int
    mean: float
    median: float
    stdev: float
    min_val: float
    max_val: float


def compute_sample_stats(values: Sequence[float]) -> StatisticalSummary:
    """Compute central tendency and dispersion metrics for numeric observations."""
    if not values:
        raise ValueError("Cannot compute statistics on an empty collection.")

    clean_vals = [float(v) for v in values if not math.isnan(v)]
    if not clean_vals:
        raise ValueError("Cannot compute statistics: all values are NaN.")

    n = len(clean_vals)
    mean_val = statistics.fmean(clean_vals)
    median_val = statistics.median(clean_vals)
    stdev_val = statistics.stdev(clean_vals) if n > 1 else 0.0

    return StatisticalSummary(
        sample_count=n,
        mean=round(mean_val, 4),
        median=round(median_val, 4),
        stdev=round(stdev_val, 4),
        min_val=min(clean_vals),
        max_val=max(clean_vals),
    )


def compute_z_score(actual: float, mean: float, stdev: float) -> float:
    """Compute the standardized Z-score = (actual - mean) / stdev.

    Returns 0.0 if stdev is zero or practically negligible.
    """
    if stdev <= 1e-9:
        # No variance in historical distribution
        return 0.0 if math.isclose(actual, mean, abs_tol=1e-9) else (999.0 if actual > mean else -999.0)
    return round((actual - mean) / stdev, 4)


def compute_percentage_deviation(
    actual: float,
    baseline: float,
) -> tuple[float, float]:
    """Safely compute absolute difference and percentage deviation between actual and baseline.

    Returns:
        (diff, pct_deviation):
        - diff = actual - baseline
        - pct_deviation = (|diff| / |baseline|) * 100.0 (or 0.0 if both are 0, or 100.0 if baseline is 0)
    """
    diff = actual - baseline

    if math.isclose(baseline, 0.0, abs_tol=1e-9):
        if math.isclose(actual, 0.0, abs_tol=1e-9):
            return 0.0, 0.0
        # When baseline is zero and actual is non-zero, deviation is technically infinite / 100%
        return diff, 100.0

    pct = (abs(diff) / abs(baseline)) * 100.0
    return round(diff, 4), round(pct, 2)


def filter_weekend_observations(
    points: Sequence[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    """Filter out observations that occurred on weekends (Saturday=5, Sunday=6)."""
    return [(dt, val) for dt, val in points if dt.weekday() < 5]
