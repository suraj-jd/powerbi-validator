# Local SQLite Database Backup & Restore Design Notes

**Status:** Design specification (Stage 2) - full UI & automation scheduled for **Stage 14**.

## Goals
- Protect user-configured workspace registrations, validation rules, and immutable run history against accidental deletion, corruption, or schema upgrade failures.
- Keep backups strictly free of authentication tokens, passwords, or secrets (tokens live only in the Windows DPAPI-protected MSAL cache, never in SQLite).

## Backup Strategy (SQLite Online Backup API)
1. **Never copy the raw `.db` file while active WAL transactions may be open.**
2. Use Python's `sqlite3.Connection.backup()` API to create a consistent point-in-time snapshot into a user-selected `.db` file or timestamped backup directory (`backups/validation_tool_YYYYMMDD_HHMMSS.db`).
3. Record a companion JSON manifest (app version, Alembic revision ID, UTC timestamp, SHA-256 checksum).
4. Automatically take a pre-migration backup snapshot whenever Alembic detects a pending schema upgrade on an existing database.

## Restore Strategy (Validation + Confirmation)
1. Validate the selected backup file before touching the active database:
   - Confirm valid SQLite header and run `PRAGMA integrity_check;`.
   - Confirm presence of `alembic_version` and required core tables (`workspace_registrations`, `validation_rules`, `validation_runs`).
   - Reject backups from a newer incompatible schema revision with a clear message.
2. Prompt the user with `ConfirmDialog(destructive=True)` summarizing the backup timestamp, run count, and warning that current local data will be replaced.
3. Take an automatic safety backup of the current database before replacing it.
4. Dispose all SQLAlchemy engine connections, swap the file atomically, run `alembic upgrade head` if the backup is from an older schema revision, and reload UI state.

## Retention & Deletion
- Honor `AppConfig.history_retention_days` for pruning old `validation_runs` / `refresh_records` when retention cleanup is implemented in Stage 14.
- Provide an explicit "Delete Local Data" action (with confirmation) to satisfy BRD Section 8.4.
