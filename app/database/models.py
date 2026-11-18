"""SQLAlchemy ORM models for the local SQLite database (BRD Section 12)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base class for all local SQLite tables."""


class AppSetting(Base):
    """Non-secret key/value settings persisted locally (BRD 12.1)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class WorkspaceRegistration(Base):
    """Registered Power BI workspace, report, and semantic model (BRD 12.2)."""

    __tablename__ = "workspace_registrations"
    __table_args__ = (
        # Prevents duplicate registrations for the same workspace + dataset + report,
        # while allowing multiple distinct reports to share one semantic model.
        UniqueConstraint(
            "workspace_id",
            "dataset_id",
            "report_id",
            name="uq_workspace_dataset_report",
        ),
        Index(
            "uq_workspace_dataset_null_report",
            "workspace_id",
            "dataset_id",
            unique=True,
            sqlite_where=text("report_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_name: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    report_name: Mapped[str] = mapped_column(String(255), nullable=False)
    report_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    rules: Mapped[list[ValidationRule]] = relationship(
        back_populates="workspace_registration",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list[ValidationRun]] = relationship(
        back_populates="workspace_registration",
        cascade="all, delete-orphan",
    )
    refresh_records: Mapped[list[RefreshRecord]] = relationship(
        back_populates="workspace_registration",
        cascade="all, delete-orphan",
    )


class ValidationRule(Base):
    """Individual user-configured validation rule (BRD 12.3)."""

    __tablename__ = "validation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_registration_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    measure_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    workspace_registration: Mapped[WorkspaceRegistration] = relationship(back_populates="rules")
    results: Mapped[list[ValidationResult]] = relationship(back_populates="validation_rule")


class ValidationRun(Base):
    """Immutable record of one validation execution (BRD 12.4)."""

    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_registration_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False)

    workspace_registration: Mapped[WorkspaceRegistration] = relationship(back_populates="runs")
    results: Mapped[list[ValidationResult]] = relationship(
        back_populates="validation_run",
        cascade="all, delete-orphan",
    )


class ValidationResult(Base):
    """Immutable per-rule result recorded inside a ValidationRun (BRD 12.5)."""

    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SET NULL preserves historical results even if a rule is later deleted.
    validation_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("validation_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    deviation: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    detailed_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    validation_run: Mapped[ValidationRun] = relationship(back_populates="results")
    validation_rule: Mapped[ValidationRule | None] = relationship(back_populates="results")


class RefreshRecord(Base):
    """Locally stored Power BI dataset refresh history record (BRD 12.6)."""

    __tablename__ = "refresh_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_registration_id: Mapped[int] = mapped_column(
        ForeignKey("workspace_registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    refresh_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refresh_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    workspace_registration: Mapped[WorkspaceRegistration] = relationship(
        back_populates="refresh_records"
    )
