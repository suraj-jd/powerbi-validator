"""Dialog for local database backup, integrity verification, restore, and historical pruning (Stage 14)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.status import NotificationLevel
from app.database.db import DatabaseManager
from app.services.backup_service import (
    backup_database,
    count_runs_older_than,
    get_database_stats,
    prune_history,
    restore_database_backup,
    vacuum_database,
    validate_database_backup,
)
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.widgets.notification_banner import NotificationBanner


class BackupMaintenanceDialog(QDialog):
    """Database management dialog providing backup, integrity check, restore, and history pruning."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db_manager
        self.setWindowTitle("Database Backup & Maintenance")
        self.setMinimumSize(680, 560)
        self.resize(760, 640)
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget(scroll_area)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header Title
        title_block = QVBoxLayout()
        title_block.setSpacing(4)
        title = QLabel("Database Backup & Storage Maintenance")
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        title_block.addWidget(title)

        desc = QLabel(
            "Manage your local SQLite storage, create transaction-safe backups, "
            "verify data integrity, optimize database space, and prune aged test history."
        )
        desc.setObjectName("PageSubtitle")
        desc.setStyleSheet("font-size: 12px; color: #64748B;")
        desc.setWordWrap(True)
        title_block.addWidget(desc)
        layout.addLayout(title_block)

        # Notification Banner
        self.banner = NotificationBanner(container)
        layout.addWidget(self.banner)

        # Card 0: Live Database Health & Metrics Overview
        self.card_stats = QFrame()
        self.card_stats.setObjectName("Card")
        self.card_stats.setStyleSheet(
            "background-color: #FFFFFF; border: 1.5px solid #E2E8F0; border-radius: 8px; padding: 14px;"
        )
        lay_s = QVBoxLayout(self.card_stats)
        lay_s.setContentsMargins(14, 12, 14, 12)
        lay_s.setSpacing(8)

        head_s = QHBoxLayout()
        lbl_s_title = QLabel("Database Health & Storage Status")
        lbl_s_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        head_s.addWidget(lbl_s_title)
        head_s.addStretch(1)

        self.btn_vacuum = QPushButton("⚡  Compact Database (VACUUM)")
        self.btn_vacuum.setObjectName("SecondaryButton")
        self.btn_vacuum.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_vacuum.setToolTip("Defragment database pages and reclaim unused disk space")
        self.btn_vacuum.clicked.connect(self._handle_vacuum)
        head_s.addWidget(self.btn_vacuum)

        self.btn_refresh_stats = QPushButton("🔄 Refresh")
        self.btn_refresh_stats.setObjectName("SecondaryButton")
        self.btn_refresh_stats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_stats.clicked.connect(self._refresh_stats)
        head_s.addWidget(self.btn_refresh_stats)
        lay_s.addLayout(head_s)

        # Path label
        self.lbl_path = QLabel()
        self.lbl_path.setStyleSheet("font-size: 11px; color: #475569; font-family: Consolas, monospace;")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay_s.addWidget(self.lbl_path)

        # Metrics pill row
        self.lbl_metrics = QLabel()
        self.lbl_metrics.setStyleSheet("font-size: 12px; font-weight: 600; color: #1E40AF;")
        lay_s.addWidget(self.lbl_metrics)

        # Date range
        self.lbl_dates = QLabel()
        self.lbl_dates.setStyleSheet("font-size: 11px; color: #64748B;")
        lay_s.addWidget(self.lbl_dates)

        layout.addWidget(self.card_stats)

        # Card 1: Create Backup
        box_backup = QFrame()
        box_backup.setObjectName("Card")
        box_backup.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;"
        )
        lay_b = QVBoxLayout(box_backup)
        lay_b.setContentsMargins(14, 12, 14, 12)
        lay_b.setSpacing(8)

        lbl_b_t = QLabel("1. Create Database Backup Snapshot")
        lbl_b_t.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        lay_b.addWidget(lbl_b_t)

        lbl_b_d = QLabel(
            "Capture a transaction-safe live snapshot of your complete SQLite database "
            "(workspaces, validation rules, runs, and results) without interrupting active validations."
        )
        lbl_b_d.setStyleSheet("font-size: 11px; color: #64748B;")
        lbl_b_d.setWordWrap(True)
        lay_b.addWidget(lbl_b_d)

        btn_backup = QPushButton("💾  Create Database Backup...")
        btn_backup.setObjectName("PrimaryButton")
        btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_backup.clicked.connect(self._handle_create_backup)
        lay_b.addWidget(btn_backup, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(box_backup)

        # Card 2: Verify & Restore
        box_restore = QFrame()
        box_restore.setObjectName("Card")
        box_restore.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;"
        )
        lay_r = QVBoxLayout(box_restore)
        lay_r.setContentsMargins(14, 12, 14, 12)
        lay_r.setSpacing(8)

        lbl_r_t = QLabel("2. Verify & Restore Backup")
        lbl_r_t.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        lay_r.addWidget(lbl_r_t)

        lbl_r_d = QLabel(
            "Inspect backup integrity before restoration. A pre-restore safety snapshot "
            "is automatically saved to your disk prior to applying the backup."
        )
        lbl_r_d.setStyleSheet("font-size: 11px; color: #64748B;")
        lbl_r_d.setWordWrap(True)
        lay_r.addWidget(lbl_r_d)

        btn_row_r = QHBoxLayout()
        btn_row_r.setSpacing(10)

        btn_verify = QPushButton("🔍  Verify Backup Integrity...")
        btn_verify.setObjectName("SecondaryButton")
        btn_verify.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_verify.clicked.connect(self._handle_verify_backup)
        btn_row_r.addWidget(btn_verify)

        btn_restore = QPushButton("⚠️  Restore from Backup Snapshot...")
        btn_restore.setObjectName("SecondaryButton")
        btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_restore.clicked.connect(self._handle_restore_backup)
        btn_row_r.addWidget(btn_restore)

        btn_row_r.addStretch(1)
        lay_r.addLayout(btn_row_r)
        layout.addWidget(box_restore)

        # Card 3: Prune Run History
        box_prune = QFrame()
        box_prune.setObjectName("Card")
        box_prune.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;"
        )
        lay_p = QVBoxLayout(box_prune)
        lay_p.setContentsMargins(14, 12, 14, 12)
        lay_p.setSpacing(8)

        lbl_p_t = QLabel("3. History Retention & Pruning")
        lbl_p_t.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        lay_p.addWidget(lbl_p_t)

        lbl_p_d = QLabel(
            "Delete old validation execution logs and test results to free up database storage. "
            "Validation rules and workspace registrations are never deleted."
        )
        lbl_p_d.setStyleSheet("font-size: 11px; color: #64748B;")
        lbl_p_d.setWordWrap(True)
        lay_p.addWidget(lbl_p_d)

        prune_row = QHBoxLayout()
        prune_row.setSpacing(10)
        lbl_keep = QLabel("Keep historical runs for (days):")
        lbl_keep.setStyleSheet("font-size: 12px; color: #334155; font-weight: 600;")
        prune_row.addWidget(lbl_keep)

        self.spin_retention = QSpinBox()
        self.spin_retention.setRange(1, 3650)
        self.spin_retention.setValue(90)
        self.spin_retention.setStyleSheet("padding: 4px 8px; font-size: 12px;")
        self.spin_retention.valueChanged.connect(self._update_prune_preview)
        prune_row.addWidget(self.spin_retention)

        self.btn_prune = QPushButton("🗑️  Prune Old Runs")
        self.btn_prune.setObjectName("SecondaryButton")
        self.btn_prune.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prune.clicked.connect(self._handle_prune_history)
        prune_row.addWidget(self.btn_prune)
        prune_row.addStretch(1)
        lay_p.addLayout(prune_row)

        self.lbl_prune_info = QLabel("Calculating prune candidate runs...")
        self.lbl_prune_info.setStyleSheet("font-size: 11px; color: #B45309; font-weight: 600;")
        lay_p.addWidget(self.lbl_prune_info)

        layout.addWidget(box_prune)
        layout.addStretch(1)

        scroll_area.setWidget(container)
        outer_layout.addWidget(scroll_area)

        # Dialog Footer
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 12, 24, 14)
        footer.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryButton")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        outer_layout.addLayout(footer)

    def _refresh_stats(self) -> None:
        try:
            stats = get_database_stats(self._db)
            self.lbl_path.setText(f"Database File: {stats['db_path']}")
            self.lbl_metrics.setText(
                f"Storage Size: {stats['file_size_display']}  •  "
                f"Runs: {stats['runs_count']}  •  "
                f"Results: {stats['results_count']}  •  "
                f"Rules: {stats['rules_count']}  •  "
                f"Workspaces: {stats['workspaces_count']}"
            )
            oldest = stats["oldest_run"]
            newest = stats["newest_run"]
            oldest_str = oldest.strftime("%Y-%m-%d %H:%M") if oldest else "None recorded"
            newest_str = newest.strftime("%Y-%m-%d %H:%M") if newest else "None recorded"
            self.lbl_dates.setText(f"Active Execution Window: {oldest_str}  ➔  {newest_str}")
        except Exception as exc:
            self.lbl_metrics.setText("Could not query database statistics.")
            self.lbl_dates.setText(str(exc))

        self._update_prune_preview()

    def _update_prune_preview(self) -> None:
        days = self.spin_retention.value()
        try:
            eligible = count_runs_older_than(self._db, days)
            if eligible > 0:
                self.lbl_prune_info.setText(
                    f"⚠️  {eligible} validation run(s) and their detailed results are older than {days} days and will be deleted."
                )
                self.lbl_prune_info.setStyleSheet("font-size: 11px; color: #B91C1C; font-weight: 600;")
                self.btn_prune.setEnabled(True)
            else:
                self.lbl_prune_info.setText(
                    f"✓  0 runs are older than {days} days. All historical records are within the retention window."
                )
                self.lbl_prune_info.setStyleSheet("font-size: 11px; color: #15803D; font-weight: 600;")
                self.btn_prune.setEnabled(True)
        except Exception:
            self.lbl_prune_info.setText("")

    def _handle_vacuum(self) -> None:
        self.btn_vacuum.setEnabled(False)
        self.btn_vacuum.setText("Compacting...")
        try:
            new_size = vacuum_database(self._db)
            self._refresh_stats()
            self.banner.show_message(
                f"Database successfully defragmented and compacted. Current size: {round(new_size / 1024.0, 1)} KB.",
                level=NotificationLevel.SUCCESS,
                title="Database Compacted",
            )
        except Exception as exc:
            self.banner.show_message(
                f"Database compaction failed: {exc}",
                level=NotificationLevel.ERROR,
                title="Compaction Error",
            )
        finally:
            self.btn_vacuum.setEnabled(True)
            self.btn_vacuum.setText("⚡  Compact Database (VACUUM)")

    def _handle_create_backup(self) -> None:
        default_name = f"powerbi_validation_backup_{Path(self._db.db_path).stem}.db"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Database Backup",
            str(Path.home() / default_name),
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if not filename:
            return

        try:
            dest = backup_database(self._db, filename)
            sz_kb = round(dest.stat().st_size / 1024.0, 1)
            self.banner.show_message(
                f"Database backup created successfully: '{dest.name}' ({sz_kb} KB).",
                level=NotificationLevel.SUCCESS,
                title="Backup Created",
            )
        except Exception as exc:
            self.banner.show_message(
                f"Backup failed: {exc}",
                level=NotificationLevel.ERROR,
                title="Backup Error",
            )

    def _handle_verify_backup(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File to Verify",
            "",
            "SQLite Database (*.db *.bak);;All Files (*.*)",
        )
        if not filename:
            return

        valid = validate_database_backup(filename)
        if valid:
            p = Path(filename)
            sz_kb = round(p.stat().st_size / 1024.0, 1)
            self.banner.show_message(
                f"Integrity check passed! '{p.name}' ({sz_kb} KB) contains valid SQLite schema and all application tables.",
                level=NotificationLevel.SUCCESS,
                title="Backup Validated",
            )
        else:
            self.banner.show_message(
                f"Integrity check failed: '{Path(filename).name}' is corrupted or missing application tables.",
                level=NotificationLevel.ERROR,
                title="Invalid Backup",
            )

    def _handle_restore_backup(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File to Restore",
            "",
            "SQLite Database (*.db *.bak);;All Files (*.*)",
        )
        if not filename:
            return

        if not validate_database_backup(filename):
            self.banner.show_message(
                f"Selected file '{Path(filename).name}' failed integrity check. Restore aborted.",
                level=NotificationLevel.ERROR,
                title="Restore Aborted",
            )
            return

        confirm = ConfirmDialog(
            title="Confirm Database Restore",
            message=(
                f"Are you sure you want to restore the database from:\n{filename}?\n\n"
                "All current registrations, rules, and run history will be replaced with the backup's data.\n"
                "A safety backup of your current database will be saved automatically before restoring."
            ),
            confirm_label="Restore Database",
            parent=self,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            restore_database_backup(filename, self._db.db_path, db_manager=self._db)
            self._refresh_stats()
            self.banner.show_message(
                "Database restored successfully. Application state and history have been reloaded.",
                level=NotificationLevel.SUCCESS,
                title="Database Restored",
            )
        except Exception as exc:
            self.banner.show_message(
                f"Restore failed: {exc}",
                level=NotificationLevel.ERROR,
                title="Restore Error",
            )

    def _handle_prune_history(self) -> None:
        days = self.spin_retention.value()
        eligible = count_runs_older_than(self._db, days)

        if eligible == 0:
            self.banner.show_message(
                f"No validation runs found older than {days} days. Nothing to prune.",
                level=NotificationLevel.INFO,
                title="Prune Not Needed",
            )
            return

        confirm = ConfirmDialog(
            title="Confirm History Pruning",
            message=(
                f"Permanently delete {eligible} validation run(s) and their detailed test results "
                f"older than {days} days?\n\n"
                "This action cannot be undone. Workspace registrations and validation rules will NOT be touched."
            ),
            confirm_label=f"Prune {eligible} Run(s)",
            parent=self,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            pruned = prune_history(self._db, days)
            self._refresh_stats()
            self.banner.show_message(
                f"Successfully pruned {pruned} validation run(s) older than {days} days. Database compacted.",
                level=NotificationLevel.SUCCESS,
                title="History Pruned",
            )
        except Exception as exc:
            self.banner.show_message(
                f"Pruning failed: {exc}",
                level=NotificationLevel.ERROR,
                title="Pruning Error",
            )
