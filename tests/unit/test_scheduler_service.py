"""Unit tests for ValidationSchedulerService and ScheduleConfig."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.database.db import DatabaseManager
from app.services.scheduler_service import (
    DEFAULT_DAILY_TIMES,
    ScheduleConfig,
    ValidationSchedulerService,
    compute_next_run,
    format_next_run_display,
)


def test_schedule_config_serialization():
    cfg = ScheduleConfig(
        enabled=True,
        mode="daily",
        times=["08:00", "14:30", "20:00"],
        interval_minutes=180,
    )
    raw = cfg.to_json()
    loaded = ScheduleConfig.from_json(raw)

    assert loaded.enabled is True
    assert loaded.mode == "daily"
    assert loaded.times == ["08:00", "14:30", "20:00"]
    assert loaded.interval_minutes == 180


def test_schedule_config_from_empty_or_corrupt_json():
    assert ScheduleConfig.from_json(None).enabled is False
    assert ScheduleConfig.from_json("").enabled is False
    assert ScheduleConfig.from_json("{corrupt json").enabled is False


def test_compute_next_run_disabled():
    cfg = ScheduleConfig(enabled=False, times=["09:00", "18:00"])
    assert compute_next_run(cfg) is None


def test_compute_next_run_daily_next_slot_today():
    cfg = ScheduleConfig(enabled=True, mode="daily", times=["08:00", "13:00", "19:00"])
    now = datetime(2026, 11, 21, 10, 30, 0)
    nxt = compute_next_run(cfg, now)

    assert nxt is not None
    assert nxt.date() == now.date()
    assert nxt.hour == 13
    assert nxt.minute == 0


def test_compute_next_run_daily_wraps_to_tomorrow():
    cfg = ScheduleConfig(enabled=True, mode="daily", times=["08:00", "13:00", "19:00"])
    now = datetime(2026, 11, 21, 21, 30, 0)
    nxt = compute_next_run(cfg, now)

    assert nxt is not None
    assert nxt.date() == (now + timedelta(days=1)).date()
    assert nxt.hour == 8
    assert nxt.minute == 0


def test_compute_next_run_interval():
    cfg = ScheduleConfig(
        enabled=True,
        mode="interval",
        interval_minutes=120,
        last_run_at=datetime(2026, 11, 21, 10, 0, 0),
    )
    now = datetime(2026, 11, 21, 11, 0, 0)
    nxt = compute_next_run(cfg, now)

    assert nxt is not None
    assert nxt == datetime(2026, 11, 21, 12, 0, 0)


def test_format_next_run_display():
    now = datetime(2026, 11, 21, 10, 0, 0)
    t_today = datetime(2026, 11, 21, 13, 30, 0)
    disp_today = format_next_run_display(t_today, now)
    assert "Today at 13:30" in disp_today
    assert "in 3h 30m" in disp_today

    t_tomorrow = datetime(2026, 11, 22, 9, 0, 0)
    disp_tomorrow = format_next_run_display(t_tomorrow, now)
    assert "Tomorrow at 09:00" in disp_tomorrow

    assert format_next_run_display(None) == "Schedule Inactive"


def test_scheduler_service_db_persistence(tmp_path: Path, qapp):
    db_file = tmp_path / "test_scheduler.db"
    db = DatabaseManager(db_file)
    db.run_migrations()

    svc = ValidationSchedulerService(db=db)
    assert svc.config.enabled is False

    new_cfg = ScheduleConfig(
        enabled=True,
        mode="daily",
        times=["07:30", "15:00"],
    )
    svc.save_config(new_cfg)
    assert svc.is_running is True

    # Reload from fresh service instance
    svc2 = ValidationSchedulerService(db=db)
    assert svc2.config.enabled is True
    assert svc2.config.times == ["07:30", "15:00"]


def test_scheduler_service_tick_triggers_signal(qapp):
    svc = ValidationSchedulerService(db=None)
    triggered = []
    svc.schedule_triggered.connect(lambda: triggered.append(True))

    past_time = datetime.now() - timedelta(minutes=5)
    svc._config.enabled = True
    svc._next_run = past_time

    svc._on_tick()

    assert len(triggered) == 1
    assert svc.config.last_run_at is not None
    # Next run advanced
    assert svc.next_run_dt > datetime.now()
