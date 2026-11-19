"""SQLite engine, session lifecycle, and programmatic Alembic migration runner."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import PersistenceError

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def build_sqlite_url(db_path: Path) -> str:
    """Build a SQLAlchemy SQLite connection URL from a local file path."""
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _configure_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA journal_mode=WAL;")
    finally:
        cursor.close()


def create_alembic_config(db_path: Path) -> AlembicConfig:
    """Create a programmatic Alembic configuration pointing at `db_path`."""
    alembic_cfg = AlembicConfig()
    alembic_cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic_cfg.set_main_option("sqlalchemy.url", build_sqlite_url(db_path))
    alembic_cfg.attributes["configure_logger"] = False
    return alembic_cfg


class DatabaseManager:
    """Manages the local SQLite database engine, sessions, and schema migrations."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.url = build_sqlite_url(self.db_path)

        self.engine: Engine = create_engine(
            self.url,
            future=True,
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _configure_sqlite_pragmas)

        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def run_migrations(self, revision: str = "head") -> None:
        """Upgrade the SQLite database to the requested Alembic revision."""
        try:
            alembic_cfg = create_alembic_config(self.db_path)
            with self.engine.begin() as connection:
                alembic_cfg.attributes["connection"] = connection
                command.upgrade(alembic_cfg, revision)
            logger.info("SQLite database ready at %s (revision=%s)", self.db_path, revision)
        except Exception as exc:
            raise PersistenceError(
                f"Failed to migrate local SQLite database at {self.db_path}: {exc}",
                user_message="Could not initialize or upgrade the local database.",
            ) from exc

    def downgrade_migrations(self, revision: str) -> None:
        """Downgrade the SQLite database to a target revision (primarily for migration tests)."""
        try:
            alembic_cfg = create_alembic_config(self.db_path)
            with self.engine.begin() as connection:
                alembic_cfg.attributes["connection"] = connection
                command.downgrade(alembic_cfg, revision)
        except Exception as exc:
            raise PersistenceError(
                f"Failed to downgrade local SQLite database at {self.db_path}: {exc}",
                user_message="Could not downgrade the local database.",
            ) from exc

    def get_current_revision(self) -> str | None:
        """Return the active Alembic schema revision stored in the database."""
        with self.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Provide a transactional SQLAlchemy session scope."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Release all pooled SQLite connections cleanly."""
        self.engine.dispose()
        logger.debug("Disposed SQLite engine for %s", self.db_path)

    def reconnect(self) -> None:
        """Dispose current connections and reinitialize engine and session factory."""
        self.dispose()
        self.engine = create_engine(
            self.url,
            future=True,
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _configure_sqlite_pragmas)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        logger.info("Reconnected SQLite engine for %s", self.db_path)

    def vacuum(self) -> None:
        """Run SQLite VACUUM to reclaim free space and defragment database pages."""
        with self.engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT").execute(text("VACUUM;"))
        logger.info("Executed SQLite VACUUM on %s", self.db_path)
