"""About page displaying application metadata, local paths, and Stage 1 shared component demo."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_STAGE, APP_VERSION
from app.core.config import AppConfig
from app.core.status import NotificationLevel, ValidationStatus
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.models.dict_table_model import ColumnSpec
from app.ui.widgets.data_table import DataTableWidget
from app.ui.widgets.notification_banner import NotificationBanner

_DEMO_COLUMNS: list[ColumnSpec] = [
    ColumnSpec(key="sr", header="SR", alignment=Qt.AlignmentFlag.AlignCenter),
    ColumnSpec(key="component", header="Shared Component"),
    ColumnSpec(key="purpose", header="Role in Application"),
    ColumnSpec(
        key="status",
        header="Sample Status",
        alignment=Qt.AlignmentFlag.AlignCenter,
        is_status=True,
    ),
]

_DEMO_ROWS = [
    {
        "sr": 1,
        "component": "Central Config (Pydantic)",
        "purpose": "Validates non-secret local preferences",
        "status": ValidationStatus.PASS.value,
    },
    {
        "sr": 2,
        "component": "Rotating Redacted Logger",
        "purpose": "Writes rotating logs while scrubbing tokens/secrets",
        "status": ValidationStatus.PASS.value,
    },
    {
        "sr": 3,
        "component": "Sample Warning State",
        "purpose": "Illustrates amber WARNING badge rendering",
        "status": ValidationStatus.WARNING.value,
    },
    {
        "sr": 4,
        "component": "Sample Failure State",
        "purpose": "Illustrates red FAIL badge rendering",
        "status": ValidationStatus.FAIL.value,
    },
    {
        "sr": 5,
        "component": "Sample Error State",
        "purpose": "Keeps execution ERROR distinct from data FAIL",
        "status": ValidationStatus.ERROR.value,
    },
]


class AboutPage(QWidget):
    """About page with runtime diagnostics and a live preview of shared UI components."""

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        logs_dir: Path | None = None,
        db_path: Path | None = None,
        token_cache_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        self._logs_dir = logs_dir
        self._db_path = db_path
        self._token_cache_path = token_cache_path
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("PageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("PageContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # Header
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel(f"About {APP_NAME}")
        title.setObjectName("PageTitle")
        title_col.addWidget(title)

        subtitle = QLabel(
            "Local-first Windows desktop application for Power BI report and semantic model validation."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        title_col.addWidget(subtitle)

        header_row.addLayout(title_col, stretch=1)

        version_badge = QLabel(f"v{APP_VERSION}")
        version_badge.setObjectName("StageBadge")
        header_row.addWidget(version_badge, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)

        # Card 1: Application & Environment Details
        info_card = QFrame()
        info_card.setObjectName("Card")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(22, 20, 22, 20)
        info_layout.setSpacing(14)

        info_heading = QLabel("Application Details")
        info_heading.setObjectName("SectionTitle")
        info_layout.addWidget(info_heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        details = [
            ("Application:", APP_NAME),
            ("Version:", f"v{APP_VERSION}"),
            ("Current Stage:", APP_STAGE),
            ("Python Runtime:", f"{sys.version.split()[0]} ({platform.system()} {platform.release()})"),
            ("UI Framework:", f"PySide6 {pyside_version}"),
            ("Log Level:", self._config.log_level),
            ("Log Directory:", str(self._logs_dir) if self._logs_dir else "Not configured"),
            ("Local Database:", str(self._db_path) if self._db_path else "Not configured"),
            (
                "Protected Token Cache:",
                str(self._token_cache_path) if self._token_cache_path else "Not configured",
            ),
        ]

        for row_idx, (label_text, value_text) in enumerate(details):
            key_lbl = QLabel(label_text)
            key_lbl.setStyleSheet("color: #475569; font-weight: 600;")
            val_lbl = QLabel(value_text)
            val_lbl.setObjectName("BodyText")
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val_lbl.setWordWrap(True)
            grid.addWidget(key_lbl, row_idx, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(val_lbl, row_idx, 1)

        info_layout.addLayout(grid)

        if self._logs_dir is not None:
            action_row = QHBoxLayout()
            self.open_logs_button = QPushButton("Open Log Folder")
            self.open_logs_button.setObjectName("SecondaryButton")
            self.open_logs_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.open_logs_button.clicked.connect(self._open_log_folder)
            action_row.addWidget(self.open_logs_button)
            action_row.addStretch(1)
            info_layout.addLayout(action_row)

        layout.addWidget(info_card)

        # Card 2: Shared UI Components Demonstration (Stage 1 acceptance check)
        demo_card = QFrame()
        demo_card.setObjectName("Card")
        demo_layout = QVBoxLayout(demo_card)
        demo_layout.setContentsMargins(22, 20, 22, 20)
        demo_layout.setSpacing(12)

        demo_heading = QLabel("Shared UI Components Preview")
        demo_heading.setObjectName("SectionTitle")
        demo_layout.addWidget(demo_heading)

        demo_desc = QLabel(
            "Interactive verification of the reusable NotificationBanner, Qt Model/View "
            "DataTableWidget, and ConfirmDialog introduced in Stage 1."
        )
        demo_desc.setObjectName("PageSubtitle")
        demo_desc.setWordWrap(True)
        demo_layout.addWidget(demo_desc)

        self.demo_banner = NotificationBanner(self)
        demo_layout.addWidget(self.demo_banner)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.demo_notify_btn = QPushButton("Show Sample Notice")
        self.demo_notify_btn.setObjectName("SecondaryButton")
        self.demo_notify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.demo_notify_btn.clicked.connect(self._show_demo_notice)
        button_row.addWidget(self.demo_notify_btn)

        self.demo_confirm_btn = QPushButton("Test Confirm Dialog")
        self.demo_confirm_btn.setObjectName("PrimaryButton")
        self.demo_confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.demo_confirm_btn.clicked.connect(self._run_demo_confirm)
        button_row.addWidget(self.demo_confirm_btn)

        button_row.addStretch(1)
        demo_layout.addLayout(button_row)

        self.demo_table = DataTableWidget(
            columns=_DEMO_COLUMNS,
            rows=_DEMO_ROWS,
            show_search=True,
            filter_column_key="status",
            filter_options=[s.value for s in ValidationStatus],
            parent=self,
        )
        self.demo_table.setMinimumHeight(230)
        self.demo_table.table_view.setColumnWidth(0, 52)
        self.demo_table.table_view.setColumnWidth(1, 210)
        self.demo_table.table_view.setColumnWidth(2, 340)
        self.demo_table.row_activated.connect(self._on_demo_row_activated)
        demo_layout.addWidget(self.demo_table)

        layout.addWidget(demo_card)
        layout.addStretch(1)

        scroll_area.setWidget(container)
        outer.addWidget(scroll_area)

    def _open_log_folder(self) -> None:
        if self._logs_dir is not None:
            self._logs_dir.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._logs_dir)))

    def _show_demo_notice(self) -> None:
        self.demo_banner.show_message(
            "Shared NotificationBanner is active and ready for upcoming stages.",
            level=NotificationLevel.INFO,
            title="Preview",
        )

    def _run_demo_confirm(self) -> None:
        confirmed = ConfirmDialog.ask(
            self,
            title="Confirm Sample Action",
            message="Do you want to test accepting the reusable confirmation dialog?",
            detail="No local data or Power BI resources are modified by this preview.",
            confirm_text="Yes, Confirm",
            cancel_text="Cancel",
        )
        if confirmed:
            self.demo_banner.show_message(
                "Confirmation dialog accepted.",
                level=NotificationLevel.SUCCESS,
                title="Confirmed",
            )
        else:
            self.demo_banner.show_message(
                "Confirmation dialog cancelled.",
                level=NotificationLevel.WARNING,
                title="Cancelled",
            )

    def _on_demo_row_activated(self, row: dict[str, object]) -> None:
        self.demo_banner.show_message(
            f"Selected row #{row.get('sr')}: {row.get('component')} ({row.get('status')})",
            level=NotificationLevel.INFO,
            title="Row Activated",
        )
