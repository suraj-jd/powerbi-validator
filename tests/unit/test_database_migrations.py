"""Unit tests for SQLite database creation, Alembic migrations, and restart persistence."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from app.database.db import DatabaseManager
from app.database.repositories import WorkspaceRegistrationRepository

EXPECTED_TABLES = {
    "alembic_version",
    "app_settings",
    "workspace_registrations",
    "validation_rules",
    "validation_runs",
    "validation_results",
    "refresh_records",
}


def test_database_auto_creates_and_migrates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "validation_tool.db"
    db = DatabaseManager(db_path)
    try:
        db.run_migrations()

        assert db_path.exists()
        assert db.get_current_revision() == "20261118_0001"

        inspector = inspect(db.engine)
        assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))
    finally:
        db.dispose()


def test_migration_downgrade_and_reupgrade_on_existing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "upgrade_test.db"
    db = DatabaseManager(db_path)
    try:
        db.run_migrations("head")
        assert db.get_current_revision() == "20261118_0001"

        db.downgrade_migrations("base")
        assert db.get_current_revision() is None
        inspector = inspect(db.engine)
        assert "workspace_registrations" not in set(inspector.get_table_names())

        db.run_migrations("head")
        assert db.get_current_revision() == "20261118_0001"
        inspector = inspect(db.engine)
        assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))
    finally:
        db.dispose()


def test_data_survives_database_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "restart_test.db"

    db1 = DatabaseManager(db_path)
    try:
        db1.run_migrations()
        with db1.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            created = repo.create(
                workspace_name="Bosch Analytics",
                workspace_id="1234abcd-5678-9012-abcd-123456789012",
                report_name="Employee Dashboard",
                report_id="aaaa1111-2222-3333-4444-555566667777",
                dataset_name="HR Semantic Model",
                dataset_id="b7f8a12c-1234-5678-90ab-cdef12345678",
            )
            created_id = created.id
    finally:
        db1.dispose()

    # Reopen from scratch simulating an app restart
    db2 = DatabaseManager(db_path)
    try:
        db2.run_migrations()
        with db2.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            reloaded = repo.get_by_id(created_id)
            assert reloaded is not None
            assert reloaded.workspace_name == "Bosch Analytics"
            assert reloaded.report_name == "Employee Dashboard"
            assert reloaded.dataset_name == "HR Semantic Model"
    finally:
        db2.dispose()
