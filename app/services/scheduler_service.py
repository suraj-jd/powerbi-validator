"""Background validation scheduler service managing Power BI-style recurring runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
import json
import logging
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from app.database.db import DatabaseManager
from app.database.models import utc_now
from app.database.repositories.settings_repository import AppSettingsRepository

logger = logging.getLogger(__name__)

SETTING_KEY_SCHEDULER_CONFIG = "validation_scheduler_config"

DEFAULT_DAILY_TIMES = ["09:00", "13:00", "18:00"]


@dataclass
class ScheduleConfig:
    """Configuration for recurring validation schedules."""

    enabled: bool = False
    mode: str = "daily"  # "daily" or "interval"
    times: list[str] = field(default_factory=lambda: list(DEFAULT_DAILY_TIMES))
    interval_minutes: int = 240  # 4 hours
    last_run_at: datetime | None = None

    def to_json(self) -> str:
        data: dict[str, Any] = {
            "enabled": self.enabled,
            "mode": self.mode,
            "times": sorted(list(set(self.times))),
            "interval_minutes": self.interval_minutes,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, raw: str | None) -> ScheduleConfig:
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
            last_run = None
            if data.get("last_run_at"):
                try:
                    last_run = datetime.fromisoformat(data["last_run_at"])
                except Exception:
                    pass
            times = data.get("times")
            if not isinstance(times, list):
                times = list(DEFAULT_DAILY_TIMES)
            return cls(
                enabled=bool(data.get("enabled", False)),
                mode=str(data.get("mode", "daily")),
                times=sorted(list(set(str(t).strip() for t in times if str(t).strip()))),
                interval_minutes=int(data.get("interval_minutes", 240)),
                last_run_at=last_run,
            )
        except Exception as exc:
            logger.warning("Failed to parse scheduler config JSON, using default: %s", exc)
            return cls()


def compute_next_run(config: ScheduleConfig, current_dt: datetime | None = None) -> datetime | None:
    """Calculate the next scheduled execution timestamp based on local datetime."""
    if not config.enabled:
        return None

    now = current_dt or datetime.now()

    if config.mode == "interval":
        mins = max(1, config.interval_minutes)
        if config.last_run_at is None:
            # If never run, run at next clean interval boundary or now + mins
            return now + timedelta(minutes=mins)
        # Convert last_run_at to local naive if now is naive
        last = config.last_run_at
        if now.tzinfo is None and last.tzinfo is not None:
            last = last.astimezone().replace(tzinfo=None)
        elif now.tzinfo is not None and last.tzinfo is None:
            last = last.replace(tzinfo=now.tzinfo)
        nxt = last + timedelta(minutes=mins)
        return nxt if nxt > now else now + timedelta(minutes=mins)

    # Daily mode with multiple times
    if not config.times:
        return None

    # Parse and sort times
    time_objs: list[time] = []
    for t_str in config.times:
        try:
            parts = t_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            time_objs.append(time(h, m))
        except Exception:
            continue

    if not time_objs:
        return None

    time_objs.sort()

    today_date = now.date()
    # Check remaining times today
    for t in time_objs:
        candidate = datetime.combine(today_date, t)
        if now.tzinfo is not None:
            candidate = candidate.replace(tzinfo=now.tzinfo)
        if candidate > now:
            return candidate

    # If all times today have passed, pick first time tomorrow
    tomorrow_date = today_date + timedelta(days=1)
    candidate = datetime.combine(tomorrow_date, time_objs[0])
    if now.tzinfo is not None:
        candidate = candidate.replace(tzinfo=now.tzinfo)
    return candidate


def format_next_run_display(next_dt: datetime | None, now: datetime | None = None) -> str:
    """Format the next run timestamp into a concise user-friendly string."""
    if next_dt is None:
        return "Schedule Inactive"

    cur = now or datetime.now()
    if cur.tzinfo is None and next_dt.tzinfo is not None:
        next_dt = next_dt.astimezone().replace(tzinfo=None)
    elif cur.tzinfo is not None and next_dt.tzinfo is None:
        next_dt = next_dt.replace(tzinfo=cur.tzinfo)

    diff = next_dt - cur
    diff_sec = max(0, int(diff.total_seconds()))

    hours = diff_sec // 3600
    mins = (diff_sec % 3600) // 60

    if hours > 0:
        rel_str = f"in {hours}h {mins}m"
    elif mins > 0:
        rel_str = f"in {mins}m"
    else:
        rel_str = "imminent"

    time_str = next_dt.strftime("%H:%M")
    if next_dt.date() == cur.date():
        return f"Today at {time_str} ({rel_str})"
    if next_dt.date() == cur.date() + timedelta(days=1):
        return f"Tomorrow at {time_str} ({rel_str})"
    return f"{next_dt.strftime('%b %d')} at {time_str} ({rel_str})"


class ValidationSchedulerService(QObject):
    """Background service that periodically checks and triggers recurring validation runs."""

    schedule_triggered = Signal()
    schedule_config_changed = Signal(object)  # emits ScheduleConfig

    def __init__(
        self,
        db: DatabaseManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._config = ScheduleConfig()
        self._next_run: datetime | None = None
        self._is_evaluating = False

        self._timer = QTimer(self)
        self._timer.setInterval(15000)  # Check every 15 seconds
        self._timer.timeout.connect(self._on_tick)

        self._load_config()

    @property
    def config(self) -> ScheduleConfig:
        return self._config

    @property
    def next_run_dt(self) -> datetime | None:
        return self._next_run

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def set_db(self, db: DatabaseManager) -> None:
        self._db = db
        self._load_config()

    def _load_config(self) -> None:
        if self._db is None:
            self._next_run = compute_next_run(self._config)
            return

        try:
            with self._db.session_scope() as session:
                repo = AppSettingsRepository(session)
                raw = repo.get_value(SETTING_KEY_SCHEDULER_CONFIG)
                self._config = ScheduleConfig.from_json(raw)
        except Exception as exc:
            logger.warning("Could not load scheduler config: %s", exc)
            self._config = ScheduleConfig()

        self._next_run = compute_next_run(self._config)
        self._sync_timer_state()
        self.schedule_config_changed.emit(self._config)

    def save_config(self, config: ScheduleConfig) -> None:
        """Persist a new schedule configuration and update the background timer."""
        self._config = config
        self._next_run = compute_next_run(self._config)

        if self._db is not None:
            try:
                with self._db.session_scope() as session:
                    repo = AppSettingsRepository(session)
                    repo.set(SETTING_KEY_SCHEDULER_CONFIG, config.to_json())
            except Exception as exc:
                logger.error("Failed to save scheduler config to database: %s", exc)

        self._sync_timer_state()
        self.schedule_config_changed.emit(self._config)

    def mark_run_completed(self) -> None:
        """Record that a validation run was executed and advance to the next scheduled time."""
        now = datetime.now()
        self._config.last_run_at = now
        self._next_run = compute_next_run(self._config, now)
        if self._db is not None:
            try:
                with self._db.session_scope() as session:
                    repo = AppSettingsRepository(session)
                    repo.set(SETTING_KEY_SCHEDULER_CONFIG, self._config.to_json())
            except Exception as exc:
                logger.debug("Failed updating last_run_at: %s", exc)
        self.schedule_config_changed.emit(self._config)

    def _sync_timer_state(self) -> None:
        if self._config.enabled:
            if not self._timer.isActive():
                self._timer.start()
        else:
            if self._timer.isActive():
                self._timer.stop()

    def _on_tick(self) -> None:
        """Periodic tick checking if current time has reached next scheduled run."""
        if not self._config.enabled or self._is_evaluating:
            return

        if self._next_run is None:
            self._next_run = compute_next_run(self._config)
            return

        now = datetime.now()
        cur_cmp = now
        nxt_cmp = self._next_run
        if cur_cmp.tzinfo is None and nxt_cmp.tzinfo is not None:
            nxt_cmp = nxt_cmp.astimezone().replace(tzinfo=None)
        elif cur_cmp.tzinfo is not None and nxt_cmp.tzinfo is None:
            nxt_cmp = nxt_cmp.replace(tzinfo=cur_cmp.tzinfo)

        if cur_cmp >= nxt_cmp:
            logger.info("Validation schedule triggered at %s (scheduled: %s)", now, self._next_run)
            self._is_evaluating = True
            try:
                self.schedule_triggered.emit()
            finally:
                self.mark_run_completed()
                self._is_evaluating = False

    def get_status_text(self) -> str:
        """Generate human-readable status text for UI display."""
        if not self._config.enabled:
            return "Schedule Off"
        if not self._next_run:
            return "No upcoming runs"
        return format_next_run_display(self._next_run)
