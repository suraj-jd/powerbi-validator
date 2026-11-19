"""CRUD repository for Power BI refresh history records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.status import RefreshStatus
from app.database.models import RefreshRecord, utc_now


class RefreshRecordRepository:
    """Repository managing `refresh_records` persisted from Power BI refresh history."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        workspace_registration_id: int,
        dataset_id: str,
        status: str,
        refresh_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        duration_ms: int | None = None,
        refresh_type: str | None = None,
        error_details: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> RefreshRecord:
        record = RefreshRecord(
            workspace_registration_id=workspace_registration_id,
            dataset_id=dataset_id.strip().lower(),
            refresh_id=refresh_id,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            refresh_type=refresh_type,
            error_details=error_details,
            retrieved_at=retrieved_at or utc_now(),
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_by_id(self, record_id: int) -> RefreshRecord | None:
        return self._session.get(RefreshRecord, record_id)

    def list_for_registration(
        self,
        workspace_registration_id: int,
        *,
        limit: int | None = None,
    ) -> list[RefreshRecord]:
        stmt = (
            select(RefreshRecord)
            .where(RefreshRecord.workspace_registration_id == workspace_registration_id)
            .order_by(RefreshRecord.start_time.desc(), RefreshRecord.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt).all())

    def get_latest_attempt(self, workspace_registration_id: int) -> RefreshRecord | None:
        records = self.list_for_registration(workspace_registration_id, limit=1)
        return records[0] if records else None

    def get_latest_successful(self, workspace_registration_id: int) -> RefreshRecord | None:
        stmt = (
            select(RefreshRecord)
            .where(
                RefreshRecord.workspace_registration_id == workspace_registration_id,
                RefreshRecord.status == RefreshStatus.SUCCESS.value,
            )
            .order_by(RefreshRecord.start_time.desc(), RefreshRecord.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def get_latest_completed(self, workspace_registration_id: int) -> RefreshRecord | None:
        stmt = (
            select(RefreshRecord)
            .where(
                RefreshRecord.workspace_registration_id == workspace_registration_id,
                RefreshRecord.end_time.is_not(None),
            )
            .order_by(RefreshRecord.start_time.desc(), RefreshRecord.id.desc())
            .limit(1)
        )
        return self._session.scalars(stmt).first()

    def delete(self, record_id: int) -> bool:
        record = self.get_by_id(record_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True
