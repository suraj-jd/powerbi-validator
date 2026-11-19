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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.status import NotificationLevel
from app.database.db import DatabaseManager
from app.services.backup_service import (
    backup_database,
    prune_history,
    restore_database_backup,
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
        self.setMinimumSize(600, 480)
        self.resize(650, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Database Backup & History Maintenance")
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        desc = QLabel(
            "Manage local SQLite persistence, verify backup integrity, restore from snapshots, "
            "and prune historical validation runs."
        )
        desc.setObjectName("PageSubtitle")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.banner = NotificationBanner(self)
        layout.addWidget(self.banner)

        # Action 1: Create Backup
        box_backup = QFrame()
        box_backup.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;")
        lay_b = QVBoxLayout(box_backup)
        lay_b.setContentsMargins(10, 10, 10, 10)
        lay_b.setSpacing(8)

        lbl_b_t = QLabel("1. Create Database Backup")
        lbl_b_t.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A;")
        lay_b.addWidget(lbl_b_t)
        lbl_b_d = QLabel("Take a live snapshot of your local SQLite database without stopping the application.")
        lbl_b_d.setStyleSheet("font-size: 11px; color: #64748B;")
        lay_b.addWidget(lbl_b_d)

        btn_backup = QPushButton("💾  Create Backup...")
        btn_backup.setObjectName("PrimaryButton")
        btn_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_backup.clicked.connect(self._handle_create_backup)
        lay_b.addWidget(btn_backup, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(box_backup)

        # Action 2: Verify & Restore
        box_restore = QFrame()
        box_restore.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;")
        lay_r = QVBoxLayout(box_restore)
        lay_r.setContentsMargins(10, 10, 10, 10)
        lay_r.setSpacing(8)

        lbl_r_t = QLabel("2. Verify or Restore Backup")
        lbl_r_t.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A;")
        lay_r.addWidget(lbl_r_t)
        lbl_r_d = QLabel("Verify integrity of a previous backup file or restore it.")
        lbl_r_d.setStyleSheet("font-size: 11px; color: #64748B;")
        lay_r.addWidget(lbl_r_d)

        btn_row_r = QHBoxLayout()
        btn_verify = QPushButton("🔍  Verify Backup Integrity...")
        btn_verify.setObjectName("SecondaryButton")
        btn_verify.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_verify.clicked.connect(self._handle_verify_backup)
        btn_row_r.addWidget(btn_verify)

        btn_restore = QPushButton("⚠️  Restore from Backup...")
        btn_restore.setObjectName("SecondaryButton")
        btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_restore.clicked.connect(self._handle_restore_backup)
        btn_row_r.addWidget(btn_restore)
        btn_row_r.addStretch(1)
        lay_r.addLayout(btn_row_r)
        layout.addWidget(box_restore)

        # Action 3: Prune Run History
        box_prune = QFrame()
        box_prune.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;")
        lay_p = QVBoxLayout(box_prune)
        lay_p.setContentsMargins(10, 10, 10, 10)
        lay_p.setSpacing(8)

        lbl_p_t = QLabel("3. History Retention & Pruning")
        lbl_p_t.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A;")
        lay_p.addWidget(lbl_p_t)

        prune_row = QHBoxLayout()
        prune_row.setSpacing(10)
        lbl_keep = QLabel("Keep historical runs for (days):")
        lbl_keep.setStyleSheet("font-size: 12px; color: #334155;")
        prune_row.addWidget(lbl_keep)

        self.spin_retention = QSpinBox()
        self.spin_retention.setRange(7, 3650)
        self.spin_retention.setValue(90)
        prune_row.addWidget(self.spin_retention)

        btn_prune = QPushButton("Prune Old Runs")
        btn_prune.setObjectName("SecondaryButton")
        btn_prune.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_prune.clicked.connect(self._handle_prune_history)
        prune_row.addWidget(btn_prune)
        prune_row.addStretch(1)
        lay_p.addLayout(prune_row)
        layout.addWidget(box_prune)

        layout.addStretch(1)

        # Footer
        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryButton")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _handle_create_backup(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Database Backup",
            str(Path.home() / "powerbi_validation_backup.db"),
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if not filename:
            return

        try:
            dest = backup_database(self._db, filename)
            sz_kb = round(dest.stat().st_size / 1024.0, 1)
            self.banner.show_message(
                f"Database backup created successfully: {dest.name} ({sz_kb} KB).",
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
            self.banner.show_message(
                f"Backup integrity verified: '{Path(filename).name}' is valid and contains all essential schema tables.",
                level=NotificationLevel.SUCCESS,
                title="Backup Valid",
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
                "All current registrations, rules, and run history will be replaced with the backup's data."
            ),
            confirm_label="Restore Database",
            parent=self,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            restore_database_backup(filename, self._db.db_path)
            self.banner.show_message(
                "Database restored successfully. Please restart the application to reload fresh state.",
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
        confirm = ConfirmDialog(
            title="Confirm History Pruning",
            message=f"Are you sure you want to permanently delete validation runs older than {days} days?",
            confirm_label=f"Prune Runs Older Than {days} Days",
            parent=self,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            pruned = prune_history(self._db, days)
            self.banner.show_message(
                f"Pruned {pruned} validation run(s) older than {days} days.",
                level=NotificationLevel.SUCCESS,
                title="History Pruned",
            )
        except Exception as exc:
            self.banner.show_message(
                f"Pruning failed: {exc}",
                level=NotificationLevel.ERROR,
                title="Pruning Error",
            )
