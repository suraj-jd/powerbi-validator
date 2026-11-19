"""Export utilities for validation runs, audit reports, and redacted diagnostic logs (Stage 14)."""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
import platform
import sys
from typing import Any

from app import APP_NAME, APP_VERSION
from app.core.logging_config import redact_secrets
from app.services.orchestrator_service import ValidationRunSummaryDTO

logger = logging.getLogger(__name__)


def export_run_to_csv(summary: ValidationRunSummaryDTO, destination: Path | str) -> Path:
    """Export a validation execution run and its per-rule results to standard CSV."""
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with open(dest_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        # File header with metadata
        writer.writerow(["# Power BI Validation Tool - Execution Report"])
        writer.writerow(["# Run ID", summary.id])
        writer.writerow(["# Registration ID", summary.workspace_registration_id])
        writer.writerow(["# Overall Status", summary.overall_status.value])
        writer.writerow(["# Started At", summary.started_at_display])
        writer.writerow(["# Duration", summary.duration_display])
        writer.writerow(["# Total Rules", summary.total_rules])
        writer.writerow(["# Passed", summary.passed_count])
        writer.writerow(["# Failed", summary.failed_count])
        writer.writerow(["# Warnings", summary.warning_count])
        writer.writerow(["# Errors", summary.error_count])
        writer.writerow([])  # blank row

        # Table headers
        headers = [
            "Result ID",
            "Rule ID",
            "Rule Name",
            "Target",
            "Target Type",
            "Validation Type",
            "Status",
            "Actual Value",
            "Expected Value",
            "Deviation",
            "Duration (ms)",
            "Summary",
            "Detailed Message",
        ]
        writer.writerow(headers)

        for res in summary.results:
            writer.writerow([
                res.id,
                res.rule_id if res.rule_id is not None else "",
                res.rule_name,
                res.target_display,
                res.target_type,
                res.validation_type,
                res.status.value,
                res.actual_value or "",
                res.expected_value or "",
                res.deviation or "",
                res.duration_ms,
                res.result_summary,
                redact_secrets(res.detailed_message or ""),
            ])

    logger.info("Exported validation run #%s to CSV: %s", summary.id, dest_path)
    return dest_path


def export_run_to_xlsx(summary: ValidationRunSummaryDTO, destination: Path | str) -> Path:
    """Export validation execution results to styled Excel workbook using openpyxl."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()

    # Sheet 1: Results
    ws_results = wb.active
    ws_results.title = "Validation Results"

    # Styling definitions
    title_font = Font(name="Segoe UI", size=14, bold=True, color="1668DC")
    meta_font = Font(name="Segoe UI", size=10, color="475569")
    meta_val_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1668DC", end_color="1668DC", fill_type="solid")
    regular_font = Font(name="Segoe UI", size=10, color="1E293B")
    thin_side = Side(style="thin", color="E2E8F0")
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # Status fills
    status_fills = {
        "PASS": PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid"),
        "FAIL": PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"),
        "WARNING": PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"),
        "ERROR": PatternFill(start_color="F3E8FF", end_color="F3E8FF", fill_type="solid"),
    }
    status_fonts = {
        "PASS": Font(name="Segoe UI", size=10, bold=True, color="166534"),
        "FAIL": Font(name="Segoe UI", size=10, bold=True, color="991B1B"),
        "WARNING": Font(name="Segoe UI", size=10, bold=True, color="92400E"),
        "ERROR": Font(name="Segoe UI", size=10, bold=True, color="6B21A8"),
    }

    # Title block
    ws_results["A1"] = f"{APP_NAME} — Validation Execution Report"
    ws_results["A1"].font = title_font

    meta_items = [
        ("Run ID:", summary.id),
        ("Execution Time:", summary.started_at_display),
        ("Duration:", summary.duration_display),
        ("Overall Health:", summary.overall_status.value),
        ("Passed Checks:", f"{summary.passed_count} / {summary.total_rules}"),
        ("Failed Checks:", summary.failed_count),
        ("Warnings:", summary.warning_count),
        ("Errors:", summary.error_count),
    ]

    r_idx = 3
    for label, val in meta_items:
        ws_results.cell(row=r_idx, column=1, value=label).font = meta_font
        c_val = ws_results.cell(row=r_idx, column=2, value=val)
        c_val.font = meta_val_font
        if label == "Overall Health:":
            c_val.fill = status_fills.get(summary.overall_status.value, PatternFill())
            c_val.font = status_fonts.get(summary.overall_status.value, meta_val_font)
        r_idx += 1

    table_start_row = r_idx + 2
    headers = [
        "Status",
        "Rule Name",
        "Target",
        "Validation Type",
        "Actual Value",
        "Expected Value",
        "Deviation",
        "Duration (ms)",
        "Summary",
    ]

    for col_idx, h in enumerate(headers, start=1):
        cell = ws_results.cell(row=table_start_row, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center" if h in ("Status", "Duration (ms)") else "left", vertical="center")

    curr_row = table_start_row + 1
    for res in summary.results:
        st_val = res.status.value.upper()
        # Col 1: Status
        c_st = ws_results.cell(row=curr_row, column=1, value=st_val)
        c_st.font = status_fonts.get(st_val, regular_font)
        c_st.fill = status_fills.get(st_val, PatternFill())
        c_st.alignment = Alignment(horizontal="center", vertical="center")
        c_st.border = thin_border

        # Col 2-9
        values = [
            res.rule_name,
            res.target_display,
            res.validation_type,
            res.actual_value or "—",
            res.expected_value or "—",
            res.deviation or "None",
            res.duration_ms,
            res.result_summary,
        ]
        for c_offset, v in enumerate(values, start=2):
            cell = ws_results.cell(row=curr_row, column=c_offset, value=v)
            cell.font = regular_font
            cell.border = thin_border
            if c_offset == 8:  # Duration
                cell.alignment = Alignment(horizontal="right", vertical="center")
        curr_row += 1

    # Auto-adjust column widths
    for col in ws_results.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if cell.row < table_start_row:
                continue
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws_results.column_dimensions[col_letter].width = min(50, max(max_len + 3, 12))

    wb.save(dest_path)
    logger.info("Exported validation run #%s to XLSX: %s", summary.id, dest_path)
    return dest_path


def export_diagnostic_logs(
    logs_dir: Path | str,
    destination: Path | str,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Collect system logs, redact tokens, client secrets, and sensitive paths, and write diagnostics report."""
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    log_folder = Path(logs_dir)
    lines: list[str] = [
        f"=== {APP_NAME} Diagnostic Report ===",
        f"Generated At: {Path(destination).stat().st_ctime if dest_path.exists() else 'N/A'}",
        f"App Version: {APP_VERSION}",
        f"Python Version: {platform.python_version()}",
        f"Platform: {platform.platform()} ({platform.architecture()[0]})",
        f"System Encoding: {sys.getdefaultencoding()} / {sys.getfilesystemencoding()}",
        "",
        "=== Configuration & Runtime Metadata ===",
    ]

    if extra_metadata:
        for k, v in extra_metadata.items():
            lines.append(f"{k}: {redact_secrets(str(v))}")
    else:
        lines.append("No additional metadata provided.")

    lines.append("")
    lines.append("=== Application Log Content (Sanitized) ===")

    if log_folder.exists() and log_folder.is_dir():
        log_files = sorted(log_folder.glob("*.log"), key=os.path.getmtime, reverse=True)
        if not log_files:
            lines.append("No .log files found in log directory.")
        for lf in log_files[:3]:  # Top 3 most recent log files
            lines.append(f"\n--- Log File: {lf.name} ---")
            try:
                content = lf.read_text(encoding="utf-8", errors="replace")
                sanitized = redact_secrets(content)
                lines.append(sanitized)
            except Exception as exc:
                lines.append(f"[Error reading log file: {exc}]")
    else:
        lines.append("Log directory does not exist or is not a directory.")

    dest_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Exported sanitized diagnostic logs to: %s", dest_path)
    return dest_path
