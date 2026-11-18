"""Application service managing workspace, report, and semantic model registrations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import PersistenceError, ValidationConfigError
from app.database.db import DatabaseManager
from app.database.models import WorkspaceRegistration
from app.database.repositories import WorkspaceRegistrationRepository
from app.integrations.file_import import (
    ImportPreviewResult,
    RegistrationInput,
    export_blank_template,
    parse_registrations_file,
    validate_registration_fields,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RegistrationRecord:
    """Detached immutable DTO representing one saved registration."""

    id: int
    workspace_name: str
    workspace_id: str
    report_name: str
    report_id: str | None
    dataset_name: str | None
    dataset_id: str
    is_active: bool

    @property
    def unique_key(self) -> tuple[str, str, str | None]:
        return (
            self.workspace_id.lower(),
            self.dataset_id.lower(),
            self.report_id.lower() if self.report_id else None,
        )

    @classmethod
    def from_orm(cls, model: WorkspaceRegistration) -> RegistrationRecord:
        return cls(
            id=model.id,
            workspace_name=model.workspace_name,
            workspace_id=model.workspace_id,
            report_name=model.report_name,
            report_id=model.report_id,
            dataset_name=model.dataset_name,
            dataset_id=model.dataset_id,
            is_active=model.is_active,
        )


class RegistryService:
    """Coordinates validation, persistence, and CSV/XLSX import for registrations."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def list_registrations(self, *, active_only: bool = False) -> list[RegistrationRecord]:
        with self._db.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            models = repo.list_active() if active_only else repo.list_all()
            return [RegistrationRecord.from_orm(m) for m in models]

    def get_registration(self, registration_id: int) -> RegistrationRecord | None:
        with self._db.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            model = repo.get_by_id(registration_id)
            return RegistrationRecord.from_orm(model) if model is not None else None

    def create_registration(self, data: RegistrationInput) -> RegistrationRecord:
        validated, errors = validate_registration_fields(
            workspace_name=data.workspace_name,
            workspace_id=data.workspace_id,
            report_name=data.report_name,
            report_id=data.report_id or "",
            dataset_name=data.dataset_name or "",
            dataset_id=data.dataset_id,
            is_active=data.is_active,
        )
        if errors or validated is None:
            raise ValidationConfigError("; ".join(errors))

        with self._db.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            model = repo.create(
                workspace_name=validated.workspace_name,
                workspace_id=validated.workspace_id,
                report_name=validated.report_name,
                report_id=validated.report_id,
                dataset_name=validated.dataset_name,
                dataset_id=validated.dataset_id,
                is_active=validated.is_active,
            )
            logger.info(
                "Created registration id=%d workspace=%s report=%s",
                model.id,
                model.workspace_name,
                model.report_name,
            )
            return RegistrationRecord.from_orm(model)

    def update_registration(
        self,
        registration_id: int,
        data: RegistrationInput,
    ) -> RegistrationRecord:
        validated, errors = validate_registration_fields(
            workspace_name=data.workspace_name,
            workspace_id=data.workspace_id,
            report_name=data.report_name,
            report_id=data.report_id or "",
            dataset_name=data.dataset_name or "",
            dataset_id=data.dataset_id,
            is_active=data.is_active,
        )
        if errors or validated is None:
            raise ValidationConfigError("; ".join(errors))

        with self._db.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            model = repo.update(
                registration_id,
                workspace_name=validated.workspace_name,
                workspace_id=validated.workspace_id,
                report_name=validated.report_name,
                report_id=validated.report_id,
                dataset_name=validated.dataset_name,
                dataset_id=validated.dataset_id,
                is_active=validated.is_active,
            )
            logger.info("Updated registration id=%d", model.id)
            return RegistrationRecord.from_orm(model)

    def set_active(self, registration_id: int, is_active: bool) -> RegistrationRecord:
        with self._db.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            model = repo.update(registration_id, is_active=is_active)
            return RegistrationRecord.from_orm(model)

    def delete_registration(self, registration_id: int) -> bool:
        with self._db.session_scope() as session:
            repo = WorkspaceRegistrationRepository(session)
            deleted = repo.delete(registration_id)
            if deleted:
                logger.info("Deleted registration id=%d", registration_id)
            return deleted

    def preview_import(self, file_path: Path) -> ImportPreviewResult:
        existing_keys = {rec.unique_key for rec in self.list_registrations()}
        return parse_registrations_file(file_path, existing_keys=existing_keys)

    def commit_import(self, rows: list[RegistrationInput]) -> tuple[int, list[str]]:
        """Persist confirmed valid import rows and return `(saved_count, error_messages)`."""
        saved = 0
        errors: list[str] = []
        for item in rows:
            try:
                self.create_registration(item)
                saved += 1
            except (PersistenceError, ValidationConfigError) as exc:
                errors.append(f"{item.workspace_name} / {item.report_name}: {exc.user_message}")
        return saved, errors

    @staticmethod
    def export_template(file_path: Path) -> Path:
        return export_blank_template(file_path)
