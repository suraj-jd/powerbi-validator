"""Create initial Stage 2 SQLite schema.

Revision ID: 20261118_0001
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "workspace_registrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("workspace_name", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("report_name", sa.String(length=255), nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=True),
        sa.Column("dataset_name", sa.String(length=255), nullable=True),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "dataset_id",
            "report_id",
            name="uq_workspace_dataset_report",
        ),
    )
    op.create_index(
        "ix_workspace_registrations_workspace_id",
        "workspace_registrations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_registrations_dataset_id",
        "workspace_registrations",
        ["dataset_id"],
    )
    op.create_index(
        "uq_workspace_dataset_null_report",
        "workspace_registrations",
        ["workspace_id", "dataset_id"],
        unique=True,
        sqlite_where=sa.text("report_id IS NULL"),
    )

    op.create_table(
        "validation_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "workspace_registration_id",
            sa.Integer(),
            sa.ForeignKey("workspace_registrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=True),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column("measure_name", sa.String(length=255), nullable=True),
        sa.Column("validation_type", sa.String(length=64), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_validation_rules_workspace_registration_id",
        "validation_rules",
        ["workspace_registration_id"],
    )

    op.create_table(
        "validation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "workspace_registration_id",
            sa.Integer(),
            sa.ForeignKey("workspace_registrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overall_status", sa.String(length=32), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("app_version", sa.String(length=32), nullable=False),
    )
    op.create_index(
        "ix_validation_runs_workspace_registration_id",
        "validation_runs",
        ["workspace_registration_id"],
    )

    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "validation_run_id",
            sa.Integer(),
            sa.ForeignKey("validation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "validation_rule_id",
            sa.Integer(),
            sa.ForeignKey("validation_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actual_value", sa.Text(), nullable=True),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("deviation", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.String(length=512), nullable=False),
        sa.Column("detailed_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_validation_results_validation_run_id",
        "validation_results",
        ["validation_run_id"],
    )
    op.create_index(
        "ix_validation_results_validation_rule_id",
        "validation_results",
        ["validation_rule_id"],
    )

    op.create_table(
        "refresh_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "workspace_registration_id",
            sa.Integer(),
            sa.ForeignKey("workspace_registrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("refresh_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("refresh_type", sa.String(length=64), nullable=True),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_refresh_records_workspace_registration_id",
        "refresh_records",
        ["workspace_registration_id"],
    )
    op.create_index(
        "ix_refresh_records_dataset_id",
        "refresh_records",
        ["dataset_id"],
    )
    op.create_index(
        "ix_refresh_records_refresh_id",
        "refresh_records",
        ["refresh_id"],
    )


def downgrade() -> None:
    op.drop_table("refresh_records")
    op.drop_table("validation_results")
    op.drop_table("validation_runs")
    op.drop_table("validation_rules")
    op.drop_table("workspace_registrations")
    op.drop_table("app_settings")
