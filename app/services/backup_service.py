"""Database backup, restore validation, and historical retention pruning service (Stage 14)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import shutil
import sqlite3

from sqlalchemy import delete

from app.core.exceptions import PersistenceError
from app.database.db import DatabaseManager
from app.database.models import ValidationRun, utc_now

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


def restore_database_backup(backup_path: Path | str, target_db_path: Path | str) -> bool:
    """Restore database from a validated backup file."""
    b_path = Path(backup_path)
    t_path = Path(target_db_path)

    if not validate_database_backup(b_path):
        raise PersistenceError("Cannot restore: Backup file failed schema integrity validation.")

    t_path.parent.mkdir(parents=True, exist_ok=True)

    # Create safety snapshot of target if it exists
    if t_path.exists():
        pre_restore = t_path.with_suffix(".pre_restore.bak")
        shutil.copy2(t_path, pre_restore)

    try:
        # Atomic file copy
        shutil.copy2(b_path, t_path)
        logger.info("Successfully restored database from %s to %s", b_path, t_path)
        return True
    except Exception as exc:
        raise PersistenceError(f"Restore operation failed: {exc}") from exc


def prune_history(db_manager: DatabaseManager, retention_days: int) -> int:
    """Prune validation runs older than the specified retention window."""
    if retention_days < 1:
        raise ValueError("Retention days must be at least 1.")

    cutoff = utc_now() - timedelta(days=retention_days)

    with db_manager.session_scope() as session:
        # Cascade delete is configured on ValidationRun -> ValidationResult
        stmt = delete(ValidationRun).where(ValidationRun.started_at < cutoff)
        res = session.execute(stmt)
        deleted_count = res.rowcount or 0
        logger.info("Pruned %d validation runs older than %d days (cutoff: %s)", deleted_count, retention_days, cutoff)
        return deleted_count
