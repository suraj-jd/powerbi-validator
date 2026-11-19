"""Database backup, restore validation, and historical retention pruning service (Stage 14)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from sqlalchemy import delete, func, select

from app.core.exceptions import PersistenceError
from app.database.db import DatabaseManager
from app.database.models import (
    ValidationResult,
    ValidationRule,
    ValidationRun,
    WorkspaceRegistration,
    utc_now,
)

logger = logging.getLogger(__name__)

ESSENTIAL_TABLES = (
    "workspace_registrations",
    "validation_rules",
    "validation_runs",
    "validation_results",
    "app_settings",
)


def backup_database(db_manager: DatabaseManager, destination: Path | str) -> Path:
    """Create a live, transaction-safe SQLite backup file using the sqlite3 online backup API."""
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Use raw sqlite3 connection backup for clean consistency
    source_path = str(db_manager.db_path)
    if not Path(source_path).exists():
        raise PersistenceError(f"Source database file not found at: {source_path}")

    source_conn = sqlite3.connect(source_path)
    dest_conn = sqlite3.connect(str(dest_path))

    try:
        source_conn.backup(dest_conn)
        logger.info("Created SQLite database backup at: %s", dest_path)
    except Exception as exc:
        raise PersistenceError(f"Database backup failed: {exc}") from exc
    finally:
        dest_conn.close()
        source_conn.close()

    return dest_path


def validate_database_backup(backup_path: Path | str) -> bool:
    """Verify integrity of a backup SQLite file and check for required schema tables."""
    path = Path(backup_path)
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        conn = sqlite3.connect(str(path))
        cursor = conn.cursor()

        # 1. Run PRAGMA integrity_check
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchone()
        if not res or res[0] != "ok":
            logger.warning("Integrity check failed for backup %s: %s", path, res)
            conn.close()
            return False

        # 2. Check for presence of essential application tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        for tbl in ESSENTIAL_TABLES:
            if tbl not in tables:
                logger.warning("Backup missing expected table '%s'", tbl)
                return False

        return True
    except Exception as exc:
        logger.warning("Failed to validate database backup %s: %s", path, exc)
        return False


def restore_database_backup(
    backup_path: Path | str,
    target_db_path: Path | str,
    db_manager: DatabaseManager | None = None,
) -> bool:
    """Restore database from a validated backup file, disposing engine to prevent Windows file locks."""
    b_path = Path(backup_path)
    t_path = Path(target_db_path)

    if not validate_database_backup(b_path):
        raise PersistenceError("Cannot restore: Backup file failed schema integrity validation.")

    t_path.parent.mkdir(parents=True, exist_ok=True)

    # Dispose active SQLAlchemy engine handles before file operations
    if db_manager is not None:
        try:
            db_manager.dispose()
        except Exception as exc:
            logger.warning("Could not dispose db engine before restore: %s", exc)

    # Create safety snapshot of target if it exists
    if t_path.exists():
        pre_restore = t_path.with_suffix(".pre_restore.bak")
        try:
            shutil.copy2(t_path, pre_restore)
        except Exception as exc:
            logger.warning("Could not create pre-restore snapshot: %s", exc)

    # Clean up any SQLite WAL files around target
    for wal_suffix in ("-wal", "-shm"):
        wal_file = Path(f"{t_path}{wal_suffix}")
        if wal_file.exists():
            try:
                wal_file.unlink()
            except Exception as exc:
                logger.warning("Could not remove stale %s file: %s", wal_suffix, exc)

    try:
        shutil.copy2(b_path, t_path)
        logger.info("Successfully restored database from %s to %s", b_path, t_path)
    except Exception as exc:
        raise PersistenceError(f"Restore operation failed: {exc}") from exc

    # Reconnect and ensure migrations on the newly restored database
    if db_manager is not None:
        try:
            db_manager.reconnect()
            db_manager.run_migrations()
        except Exception as exc:
            logger.warning("Failed to reconnect or migrate after restore: %s", exc)

    return True


def prune_history(db_manager: DatabaseManager, retention_days: int) -> int:
    """Prune validation runs older than the specified retention window and compact database."""
    if retention_days < 1:
        raise ValueError("Retention days must be at least 1.")

    cutoff = utc_now() - timedelta(days=retention_days)

    with db_manager.session_scope() as session:
        # Find run IDs to delete
        stmt_select = select(ValidationRun.id).where(ValidationRun.started_at < cutoff)
        run_ids = session.scalars(stmt_select).all()
        if not run_ids:
            logger.info("No validation runs found older than %d days (cutoff: %s)", retention_days, cutoff)
            return 0

        # Delete associated results first for safety across SQLite configurations
        session.execute(
            delete(ValidationResult).where(ValidationResult.validation_run_id.in_(run_ids))
        )
        # Delete validation runs
        res = session.execute(
            delete(ValidationRun).where(ValidationRun.id.in_(run_ids))
        )
        deleted_count = res.rowcount or len(run_ids)
        logger.info("Pruned %d validation runs older than %d days (cutoff: %s)", deleted_count, retention_days, cutoff)

    # Reclaim freed disk space with VACUUM
    try:
        db_manager.vacuum()
    except Exception as exc:
        logger.warning("Vacuum after prune failed: %s", exc)

    return deleted_count


def count_runs_older_than(db_manager: DatabaseManager, retention_days: int) -> int:
    """Count how many validation runs exceed the retention age."""
    if retention_days < 1:
        return 0
    cutoff = utc_now() - timedelta(days=retention_days)
    with db_manager.session_scope() as session:
        stmt = select(func.count(ValidationRun.id)).where(ValidationRun.started_at < cutoff)
        return session.scalar(stmt) or 0


def vacuum_database(db_manager: DatabaseManager) -> int:
    """Run VACUUM on database and return updated file size in bytes."""
    db_manager.vacuum()
    return db_manager.db_path.stat().st_size if db_manager.db_path.exists() else 0


def format_file_size(size_bytes: int) -> str:
    """Format bytes into readable KB/MB string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024.0, 1)} KB"
    else:
        return f"{round(size_bytes / (1024.0 * 1024.0), 2)} MB"


def get_database_stats(db_manager: DatabaseManager) -> dict[str, Any]:
    """Retrieve summary metrics and sizing for the SQLite database."""
    path = db_manager.db_path
    size_bytes = path.stat().st_size if path.exists() else 0

    with db_manager.session_scope() as session:
        runs_count = session.scalar(select(func.count(ValidationRun.id))) or 0
        results_count = session.scalar(select(func.count(ValidationResult.id))) or 0
        rules_count = session.scalar(select(func.count(ValidationRule.id))) or 0
        workspaces_count = session.scalar(select(func.count(WorkspaceRegistration.id))) or 0
        oldest_run = session.scalar(select(func.min(ValidationRun.started_at)))
        newest_run = session.scalar(select(func.max(ValidationRun.started_at)))

    return {
        "db_path": str(path.resolve()),
        "file_size_bytes": size_bytes,
        "file_size_display": format_file_size(size_bytes),
        "runs_count": runs_count,
        "results_count": results_count,
        "rules_count": rules_count,
        "workspaces_count": workspaces_count,
        "oldest_run": oldest_run,
        "newest_run": newest_run,
    }
