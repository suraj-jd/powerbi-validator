"""Formatting helpers for durations, hours, and user-facing metrics."""

from __future__ import annotations


def format_hours_duration(hours: float | int | None) -> str:
    """Format an hour value into days and hours once it reaches or exceeds 48 hours.

    - Under 48 hours: formatted as hours (e.g. '0.5h', '2.0h', '24.0h', '47.9h').
    - 48 hours and above: formatted as days and hours (e.g. '2d', '2d 1h', '674d 8h').
    """
    if hours is None:
        return "-"
    h = abs(float(hours))
    if h < 48.0:
        return f"{h:.1f}h"
    days = int(h // 24)
    rem = round(h % 24, 1)
    if rem >= 24.0:
        days += 1
        rem = 0.0
    if rem == 0.0 or (rem.is_integer() and int(rem) == 0):
        return f"{days}d"
    if rem.is_integer():
        return f"{days}d {int(rem)}h"
    return f"{days}d {rem:.1f}h"
