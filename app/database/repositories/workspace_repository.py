"""CRUD repository for Power BI workspace, report, and semantic model registrations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import PersistenceError
from app.database.models import WorkspaceRegistration, utc_now


class WorkspaceRegistrationRepository:
    """Repository managing `workspace_registrations` records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        workspace_name: str,
        workspace_id: str,
        report_name: str,
        dataset_id: str,
        report_id: str | None = None,
        dataset_name: str | None = None,
        is_active: bool = True,
    ) -> WorkspaceRegistration:
        normalized_report_id = report_id.strip() if report_id and report_id.strip() else None
        record = WorkspaceRegistration(
            workspace_name=workspace_name.strip(),
            workspace_id=workspace_id.strip().lower(),
            report_name=report_name.strip(),
            report_id=normalized_report_id.lower() if normalized_report_id else None,
            dataset_name=dataset_name.strip() if dataset_name and dataset_name.strip() else None,
            dataset_id=dataset_id.strip().lower(),
            is_active=is_active,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise PersistenceError(
                f"Duplicate workspace/dataset/report registration: "
                f"workspace_id={record.workspace_id}, dataset_id={record.dataset_id}, "
                f"report_id={record.report_id}",
                user_message="This workspace, dataset, and report combination is already registered.",
            ) from exc
        return record

    def get_by_id(self, registration_id: int) -> WorkspaceRegistration | None:
        return self._session.get(WorkspaceRegistration, registration_id)

    def find_duplicate(
        self,
        *,
        workspace_id: str,
        dataset_id: str,
        report_id: str | None = None,
    ) -> WorkspaceRegistration | None:
        norm_ws = workspace_id.strip().lower()
        norm_ds = dataset_id.strip().lower()
        norm_rpt = report_id.strip().lower() if report_id and report_id.strip() else None

        stmt = select(WorkspaceRegistration).where(
            WorkspaceRegistration.workspace_id == norm_ws,
            WorkspaceRegistration.dataset_id == norm_ds,
        )
        if norm_rpt is None:
            stmt = stmt.where(WorkspaceRegistration.report_id.is_(None))
        else:
            stmt = stmt.where(WorkspaceRegistration.report_id == norm_rpt)
        return self._session.scalars(stmt).first()

    def find_by_workspace_and_dataset(
        self,
        workspace_id: str,
        dataset_id: str,
    ) -> WorkspaceRegistration | None:
        stmt = (
            select(WorkspaceRegistration)
            .where(
                WorkspaceRegistration.workspace_id == workspace_id.strip().lower(),
                WorkspaceRegistration.dataset_id == dataset_id.strip().lower(),
            )
            .order_by(WorkspaceRegistration.id.asc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def list_all(self) -> list[WorkspaceRegistration]:
        stmt = select(WorkspaceRegistration).order_by(WorkspaceRegistration.id.asc())
        return list(self._session.scalars(stmt).all())

    def list_active(self) -> list[WorkspaceRegistration]:
        stmt = (
            select(WorkspaceRegistration)
            .where(WorkspaceRegistration.is_active.is_(True))
            .order_by(WorkspaceRegistration.id.asc())
        )
        return list(self._session.scalars(stmt).all())

    def update(
        self,
        registration_id: int,
        *,
        workspace_name: str | None = None,
        workspace_id: str | None = None,
        report_name: str | None = None,
        report_id: str | None = ...,  # type: ignore[assignment]
        dataset_name: str | None = ...,  # type: ignore[assignment]
        dataset_id: str | None = None,
        is_active: bool | None = None,
    ) -> WorkspaceRegistration:
        record = self.get_by_id(registration_id)
        if record is None:
            raise PersistenceError(f"Workspace registration {registration_id} not found.")

        if workspace_name is not None:
            record.workspace_name = workspace_name.strip()
        if workspace_id is not None:
            record.workspace_id = workspace_id.strip().lower()
        if report_name is not None:
            record.report_name = report_name.strip()
        if report_id is not ...:
            record.report_id = report_id.strip().lower() if report_id and report_id.strip() else None
        if dataset_name is not ...:
            record.dataset_name = (
                dataset_name.strip() if dataset_name and dataset_name.strip() else None
            )
        if dataset_id is not None:
            record.dataset_id = dataset_id.strip().lower()
        if is_active is not None:
            record.is_active = is_active
        record.updated_at = utc_now()

        try:
            self._session.flush()
        except IntegrityError as exc:
            raise PersistenceError(
                f"Updating registration {registration_id} violates uniqueness constraints.",
                user_message="Another registration with the same workspace, dataset, and report already exists.",
            ) from exc
        return record

    def delete(self, registration_id: int) -> bool:
        record = self.get_by_id(registration_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True
