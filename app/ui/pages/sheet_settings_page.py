"""Excel-style validation settings page with menu ribbon and sheet table (Stage D).

Designed for non-technical users to configure validation rules in a clean,
spreadsheet-like view with intuitive menus, cascading dropdowns, and popup
gear configuration.
"""

from __future__ import annotations

import csv
from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.exceptions import format_safe_user_error
from app.core.status import NotificationLevel
from app.database.db import DatabaseManager
from app.integrations.powerbi.models import (
    DatasetMetadata,
    PowerBIDataset,
    PowerBIReport,
    PowerBIWorkspace,
)
from app.services.metadata_service import MetadataService
from app.services.powerbi_service import PowerBIService
from app.services.registry_service import RegistrationRecord, RegistryService
from app.services.rule_service import (
    RuleService,
    VALIDATION_TYPE_ANOMALY,
    VALIDATION_TYPE_DAX_MEASURE,
    VALIDATION_TYPE_DUPLICATE,
    VALIDATION_TYPE_LATEST_DATE,
    VALIDATION_TYPE_NULL,
    VALIDATION_TYPE_REFRESH,
    VALIDATION_TYPE_ROW_COUNT,
)
from app.services.sheet_service import (
    FRIENDLY_TEST_NAMES,
    SheetRowDTO,
    SheetService,
    TEST_NAME_TO_TYPE,
    format_rule_conditions_summary,
)
from app.ui.dialogs.sheet_rule_config_dialog import SheetRuleConfigDialog
from app.ui.theme import CHEVRON_ACTIVE_PATH, CHEVRON_DOWN_PATH
from app.ui.widgets.animated_combo import AnimatedComboBox, EditableCellCombo
from app.ui.widgets.notification_banner import NotificationBanner
from app.ui.widgets.smooth_scroller import apply_smooth_scrolling

logger = logging.getLogger(__name__)


class SheetSettingsPage(QWidget):
    """Spreadsheet-style validation management page featuring an Excel-like ribbon and interactive table."""

    sync_workspaces_requested = Signal()

    def __init__(
        self,
        *,
        db: DatabaseManager | None = None,
        sheet_service: SheetService | None = None,
        registry_service: RegistryService | None = None,
        rule_service: RuleService | None = None,
        powerbi_service: PowerBIService | None = None,
        metadata_service: MetadataService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._registry_service = registry_service or (RegistryService(db=self._db) if self._db is not None else None)
        self._rule_service = rule_service or (RuleService(db=self._db) if self._db is not None else None)
        self._sheet_service = sheet_service or (
            SheetService(
                db=self._db,
                registry_service=self._registry_service,
                rule_service=self._rule_service,
            )
            if self._db is not None
            else None
        )
        self._powerbi_service = powerbi_service
        self._metadata_service = metadata_service

        self._cached_workspaces: list[PowerBIWorkspace] = []
        self._cached_assets: dict[str, tuple[list[PowerBIDataset], list[PowerBIReport]]] = {}
        self._rows: list[SheetRowDTO] = []
        self._is_dirty: bool = False

        self._init_ui()
        self._connect_powerbi_service()
        self._connect_metadata_service()
        self._init_auto_save()
        self.reload_sheet()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload_sheet()

    def closeEvent(self, event) -> None:
        if hasattr(self, "_auto_save_timer") and self._auto_save_timer.isActive():
            self._auto_save_timer.stop()
        super().closeEvent(event)

    def _init_auto_save(self) -> None:
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(60_000)  # Auto-save every 1 minute
        self._auto_save_timer.timeout.connect(self._handle_auto_save)
        self._auto_save_timer.start()

    def _mark_dirty(self) -> None:
        self._is_dirty = True
        if hasattr(self, "lbl_auto_save"):
            self.lbl_auto_save.setStyleSheet("font-size: 11px; font-weight: 600; color: #D97706; margin-left: 8px;")
            self.lbl_auto_save.setText("● Unsaved changes (auto-saving in 1 min)")

    def _mark_clean(self, msg: str | None = None) -> None:
        self._is_dirty = False
        if hasattr(self, "lbl_auto_save"):
            now_str = datetime.now().strftime("%H:%M:%S")
            text = msg or f"✓ Saved at {now_str}"
            self.lbl_auto_save.setStyleSheet("font-size: 11px; font-weight: 600; color: #059669; margin-left: 8px;")
            self.lbl_auto_save.setText(text)

    # =========================================================================
    # UI Construction
    # =========================================================================

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(12)

        # Header Title row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        title_lbl = QLabel("Validation Sheet (Excel-Style Rule Manager)")
        title_lbl.setObjectName("PageTitle")
        title_block.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Configure and maintain Power BI validation checks in a clean, spreadsheet view. "
            "Select workspaces and reports from dropdowns — no technical IDs required."
        )
        sub_lbl.setObjectName("PageSubtitle")
        title_block.addWidget(sub_lbl)
        header_row.addLayout(title_block, stretch=1)

        badge = QLabel("Interactive Sheet Mode")
        badge.setObjectName("StageBadge")
        badge.setStyleSheet(
            "background-color: #E0E7FF; color: #3730A3; font-weight: 700; "
            "padding: 5px 12px; border-radius: 12px; font-size: 11px;"
        )
        header_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        main_layout.addLayout(header_row)

        # Top Menu Ribbon
        ribbon_frame = self._build_menu_ribbon()
        main_layout.addWidget(ribbon_frame)

        # Notification Banner
        self.banner = NotificationBanner(self)
        main_layout.addWidget(self.banner)

        # Spreadsheet Table
        self.sheet_table = self._build_sheet_table()
        main_layout.addWidget(self.sheet_table, stretch=1)

        # Bottom Summary & Status Bar
        status_bar = self._build_status_bar()
        main_layout.addLayout(status_bar)

    def _build_menu_ribbon(self) -> QFrame:
        ribbon = QFrame(self)
        ribbon.setObjectName("RibbonBar")
        ribbon.setStyleSheet(
            "#RibbonBar { background-color: #FFFFFF; border: 1px solid #CBD5E1; "
            "border-radius: 8px; padding: 4px 8px; }"
        )
        ribbon_layout = QHBoxLayout(ribbon)
        ribbon_layout.setContentsMargins(6, 4, 6, 4)
        ribbon_layout.setSpacing(6)

        # Group 1: Sheet Actions
        self.btn_add_row = QPushButton("➕ Add Row")
        self.btn_add_row.setObjectName("PrimaryButton")
        self.btn_add_row.setToolTip("Add a new validation rule row")
        self.btn_add_row.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 5px 10px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_add_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_row.clicked.connect(self._handle_add_row)
        ribbon_layout.addWidget(self.btn_add_row)

        self.btn_delete_row = QPushButton("🗑️ Delete")
        self.btn_delete_row.setObjectName("SecondaryButton")
        self.btn_delete_row.setToolTip("Delete the selected validation row")
        self.btn_delete_row.setStyleSheet(
            "padding: 5px 10px; font-size: 12px; border-radius: 5px;"
        )
        self.btn_delete_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_row.clicked.connect(self._handle_delete_selected_row)
        ribbon_layout.addWidget(self.btn_delete_row)

        self.btn_save_sheet = QPushButton("💾 Save Sheet")
        self.btn_save_sheet.setObjectName("PrimaryButton")
        self.btn_save_sheet.setToolTip("Save all validation rules to local database")
        self.btn_save_sheet.setStyleSheet(
            "background-color: #10B981; color: #FFFFFF; font-weight: 700; padding: 5px 12px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_save_sheet.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_sheet.clicked.connect(self._handle_save_sheet)
        ribbon_layout.addWidget(self.btn_save_sheet)

        self._add_ribbon_separator(ribbon_layout)

        # Group 2: Power BI Sync
        self.btn_sync_pbi = QPushButton("🔄 Sync PBI")
        self.btn_sync_pbi.setObjectName("SecondaryButton")
        self.btn_sync_pbi.setToolTip("Fetch accessible workspaces and datasets from Power BI")
        self.btn_sync_pbi.setStyleSheet(
            "padding: 5px 10px; font-size: 12px; border-radius: 5px;"
        )
        self.btn_sync_pbi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync_pbi.clicked.connect(self._handle_sync_powerbi)
        ribbon_layout.addWidget(self.btn_sync_pbi)

        self._add_ribbon_separator(ribbon_layout)

        # Group 3: File Transfer
        self.btn_import = QPushButton("📥 Import...")
        self.btn_import.setObjectName("SecondaryButton")
        self.btn_import.setToolTip("Import validation rules from Excel or CSV with template support")
        self.btn_import.setStyleSheet(
            "padding: 5px 10px; font-size: 12px; border-radius: 5px;"
        )
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self._handle_import_sheet)
        ribbon_layout.addWidget(self.btn_import)

        self.btn_export = QPushButton("📤 Export...")
        self.btn_export.setObjectName("SecondaryButton")
        self.btn_export.setToolTip("Export validation sheet to Excel (.xlsx) or CSV")
        self.btn_export.setStyleSheet(
            "padding: 5px 10px; font-size: 12px; border-radius: 5px;"
        )
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._handle_export_sheet)
        ribbon_layout.addWidget(self.btn_export)

        ribbon_layout.addStretch(1)

        # Group 4: Quick Search
        self.search_filter = QLineEdit()
        self.search_filter.setObjectName("RibbonSearch")
        self.search_filter.setPlaceholderText("🔍 Filter...")
        self.search_filter.setMinimumWidth(80)
        self.search_filter.setMaximumWidth(150)
        self.search_filter.setStyleSheet(
            "QLineEdit#RibbonSearch { background: #F8FAFC; border: 1px solid #CBD5E1; "
            "border-radius: 4px; padding: 4px 8px; font-size: 11px; } "
            "QLineEdit#RibbonSearch:focus { border-color: #1668DC; background: #FFFFFF; }"
        )
        self.search_filter.textChanged.connect(self._apply_filter)
        ribbon_layout.addWidget(self.search_filter)

        return ribbon

    def _add_ribbon_separator(self, layout: QHBoxLayout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #E2E8F0; margin: 2px 2px; max-width: 1px;")
        layout.addWidget(sep)

    def _build_sheet_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName("SheetTable")
        table.setColumnCount(13)
        table.setHorizontalHeaderLabels([
            "Sr.",
            "Enabled",
            "Workspace",
            "Report / Dataset",
            "Test to Do",
            "Table Name",
            "Column or Measure",
            "Filter 1",
            "Filter 2",
            "Filter 3",
            "Filter 4",
            "Test Rule & Settings ⚙️",
            "Action",
        ])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.resizeSection(0, 38)   # Sr.
        header.resizeSection(1, 55)   # Enabled
        header.resizeSection(2, 140)  # Workspace
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(3, 170)  # Report / Dataset
        header.resizeSection(4, 150)  # Test to Do
        header.resizeSection(5, 120)  # Table Name
        header.resizeSection(6, 130)  # Column or Measure
        header.resizeSection(7, 130)  # Filter 1
        header.resizeSection(8, 130)  # Filter 2
        header.resizeSection(9, 130)  # Filter 3
        header.resizeSection(10, 130) # Filter 4
        header.resizeSection(11, 180) # Settings
        header.resizeSection(12, 45)  # Action

        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        apply_smooth_scrolling(table)
        table.setStyleSheet(
            "QTableWidget#SheetTable { "
            "  background-color: #FFFFFF; "
            "  alternate-background-color: #F8FAFC; "
            "  gridline-color: #E2E8F0; "
            "  border: 1px solid #CBD5E1; "
            "  border-radius: 4px; "
            "  font-size: 12px; "
            "  selection-background-color: #EFF6FF; "
            "  selection-color: #0F172A; "
            "} "
            "QTableWidget#SheetTable::item { "
            "  padding: 0px; "
            "  margin: 0px; "
            "  border: none; "
            "} "
            "QTableWidget#SheetTable QHeaderView::section { "
            "  background-color: #F1F5F9; "
            "  color: #0F172A; "
            "  font-weight: 700; "
            "  font-size: 11px; "
            "  border: none; "
            "  border-right: 1px solid #CBD5E1; "
            "  border-bottom: 1.5px solid #CBD5E1; "
            "  padding: 6px 8px; "
            "} "
            "QComboBox#SheetCellCombo { "
            "  combobox-popup: 0; "
            "  border: 1px solid #CBD5E1; "
            "  border-radius: 4px; "
            "  background-color: #FFFFFF; "
            "  padding: 2px 20px 2px 7px; "
            "  margin: 1px 2px; "
            "  font-size: 12px; "
            "  color: #0F172A; "
            "} "
            "QComboBox#SheetCellCombo:hover { "
            "  border: 1.5px solid #1668DC; "
            "  background-color: #F8FAFC; "
            "} "
            "QComboBox#SheetCellCombo:focus { "
            "  border: 1.5px solid #1668DC; "
            "  background-color: #FFFFFF; "
            "} "
            "QComboBox#SheetCellCombo:disabled { "
            "  background-color: #F8FAFC; "
            "  color: #94A3B8; "
            "  border-color: #E2E8F0; "
            "} "
            "QComboBox#SheetCellCombo QLineEdit { "
            "  border: none; "
            "  background: transparent; "
            "  padding: 0px; "
            "  margin: 0px; "
            "  font-size: 12px; "
            "  color: #0F172A; "
            "} "
            "QComboBox#SheetCellCombo:disabled QLineEdit { "
            "  color: #94A3B8; "
            "  font-style: italic; "
            "} "
            "QComboBox#SheetCellCombo::drop-down { "
            "  subcontrol-origin: padding; "
            "  subcontrol-position: top right; "
            "  width: 18px; "
            "  border-left: none; "
            "} "
            f"QComboBox#SheetCellCombo::down-arrow {{ "
            f"  image: url('{CHEVRON_DOWN_PATH}'); "
            f"  width: 9px; height: 9px; "
            f"}} "
            f"QComboBox#SheetCellCombo::down-arrow:hover, QComboBox#SheetCellCombo::down-arrow:focus {{ "
            f"  image: url('{CHEVRON_ACTIVE_PATH}'); "
            f"}} "
            "QLineEdit#SheetCellInput { "
            "  border: 1px solid transparent; "
            "  border-radius: 0px; "
            "  background-color: transparent; "
            "  padding: 2px 6px; "
            "  margin: 1px; "
            "  font-size: 12px; "
            "  color: #0F172A; "
            "} "
            "QLineEdit#SheetCellInput:hover { "
            "  border: 1px solid #94A3B8; "
            "  background-color: #FFFFFF; "
            "} "
            "QLineEdit#SheetCellInput:focus { "
            "  border: 1.5px solid #1668DC; "
            "  background-color: #FFFFFF; "
            "} "
            "QLineEdit#SheetCellInput:disabled { "
            "  color: #94A3B8; "
            "  background-color: #F8FAFC; "
            "  font-style: italic; "
            "} "
            "QPushButton#SheetCellGear { "
            "  text-align: left; "
            "  padding: 2px 8px; "
            "  font-size: 11px; "
            "  font-weight: 500; "
            "  background-color: #F1F5F9; "
            "  border: 1px solid #CBD5E1; "
            "  border-radius: 3px; "
            "  margin: 2px 4px; "
            "  color: #1E293B; "
            "} "
            "QPushButton#SheetCellGear:hover { "
            "  background-color: #E2E8F0; "
            "  border-color: #94A3B8; "
            "  color: #0F172A; "
            "} "
            "QPushButton#SheetCellDelete { "
            "  background-color: transparent; "
            "  border: none; "
            "  border-radius: 3px; "
            "  font-size: 13px; "
            "  padding: 2px; "
            "  margin: 2px; "
            "} "
            "QPushButton#SheetCellDelete:hover { "
            "  background-color: #FEE2E2; "
            "}"
        )
        return table

    def _build_status_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(16)

        self.lbl_row_stats = QLabel("Total Rows: 0  |  Enabled: 0  |  Workspaces: 0")
        self.lbl_row_stats.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        bar.addWidget(self.lbl_row_stats)

        self.lbl_auto_save = QLabel("✓ Auto-save active (1 min)")
        self.lbl_auto_save.setStyleSheet("font-size: 11px; font-weight: 600; color: #059669; margin-left: 8px;")
        bar.addWidget(self.lbl_auto_save)

        bar.addStretch(1)

        hint = QLabel("💡 Tip: Click the ⚙️ gear button to customize allowed blanks, freshness SLA, deviation %, or baselines.")
        hint.setStyleSheet("font-size: 11px; color: #64748B; font-style: italic;")
        bar.addWidget(hint)

        return bar

    # =========================================================================
    # Data Loading & Table Population
    # =========================================================================

    def reload_sheet(self) -> None:
        """Reload all sheet rows from the sheet service / SQLite database."""
        if self._sheet_service is None:
            return

        try:
            self._rows = self._sheet_service.load_sheet_rows()
            self._populate_table()
            self._update_stats_label()
        except Exception as exc:
            logger.exception("Failed to load sheet rows: %s", exc)
            self.banner.show_message(
                f"Error loading validation sheet: {format_safe_user_error(exc)}",
                level=NotificationLevel.ERROR,
                title="Load Failed",
            )

    def _populate_table(self) -> None:
        self.sheet_table.setRowCount(0)
        self.sheet_table.setRowCount(len(self._rows))

        for row_idx, dto in enumerate(self._rows):
            self._render_row_cells(row_idx, dto)

        self._apply_filter(self.search_filter.text())

    def _render_row_cells(self, row_idx: int, dto: SheetRowDTO) -> None:
        # Col 0: Sr. No
        sr_item = QTableWidgetItem(str(row_idx + 1))
        sr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        sr_item.setFlags(sr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.sheet_table.setItem(row_idx, 0, sr_item)

        # Col 1: Enabled Checkbox
        chk_widget = QWidget()
        chk_widget.setStyleSheet("background: transparent;")
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk = QCheckBox()
        chk.setChecked(dto.enabled)
        chk.toggled.connect(lambda state, r=dto: self._on_row_enabled_changed(state, r))
        chk_layout.addWidget(chk)
        self.sheet_table.setCellWidget(row_idx, 1, chk_widget)

        # Col 2: Workspace Dropdown
        ws_combo = AnimatedComboBox()
        ws_combo.setObjectName("SheetCellCombo")
        self._populate_workspace_combo(ws_combo, selected_id=dto.workspace_id, selected_name=dto.workspace_name)
        self.sheet_table.setCellWidget(row_idx, 2, ws_combo)

        # Col 3: Report / Dataset Dropdown
        ds_combo = AnimatedComboBox()
        ds_combo.setObjectName("SheetCellCombo")
        self._populate_dataset_combo(
            ds_combo,
            workspace_id=dto.workspace_id,
            selected_ds_id=dto.dataset_id,
            selected_report_name=dto.report_name,
        )
        self.sheet_table.setCellWidget(row_idx, 3, ds_combo)

        # Col 4: Test to Do Dropdown
        test_combo = AnimatedComboBox()
        test_combo.setObjectName("SheetCellCombo")
        for key, friendly in FRIENDLY_TEST_NAMES.items():
            test_combo.addItem(friendly, key)
        # Select matching
        cur_test_idx = next(
            (i for i in range(test_combo.count()) if test_combo.itemData(i) == dto.validation_type),
            0,
        )
        test_combo.setCurrentIndex(cur_test_idx)
        self.sheet_table.setCellWidget(row_idx, 4, test_combo)

        # Col 5: Table Name Dropdown
        tbl_combo = EditableCellCombo()
        tbl_combo.setObjectName("SheetCellCombo")
        self._populate_table_combo(
            tbl_combo,
            workspace_id=dto.workspace_id,
            dataset_id=dto.dataset_id,
            selected_tbl=dto.table_name,
        )
        self.sheet_table.setCellWidget(row_idx, 5, tbl_combo)

        # Col 6: Column or Measure Dropdown
        col_combo = EditableCellCombo()
        col_combo.setObjectName("SheetCellCombo")
        selected_target = dto.measure_name if dto.measure_name else (dto.column_name or "")
        self._populate_column_measure_combo(
            col_combo,
            workspace_id=dto.workspace_id,
            dataset_id=dto.dataset_id,
            table_name=dto.table_name,
            selected_val=selected_target,
            validation_type=dto.validation_type,
        )
        self.sheet_table.setCellWidget(row_idx, 6, col_combo)

        # Cols 7-10: Filter 1, Filter 2, Filter 3, Filter 4
        filter_edits: list[QLineEdit] = []
        for f_idx, col_num in enumerate(range(7, 11), start=1):
            prop_name = f"filter_{f_idx}"
            cur_val = getattr(dto, prop_name, "") or dto.config.get(prop_name, "") or ""
            f_edit = QLineEdit(str(cur_val))
            f_edit.setObjectName(f"FilterInput_{f_idx}")
            f_edit.setPlaceholderText(f"Filter {f_idx} (e.g. 'Dates'[Year]=2024)")
            f_edit.setToolTip(f"DAX filter condition {f_idx} passed to CALCULATE / CALCULATETABLE (e.g. 'Table'[Col] = \"Val\")")
            f_edit.setStyleSheet(
                "QLineEdit { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 3px; "
                "padding: 2px 5px; font-size: 11px; font-family: Consolas, 'Courier New', monospace; color: #0F172A; } "
                "QLineEdit:focus { border: 1px solid #1668DC; background: #F8FAFC; } "
                "QLineEdit:disabled { background: #F1F5F9; color: #94A3B8; border-color: #E2E8F0; }"
            )
            f_edit.textChanged.connect(
                lambda txt, r=dto, p=prop_name: self._on_row_filter_changed(txt, r, p)
            )
            self.sheet_table.setCellWidget(row_idx, col_num, f_edit)
            filter_edits.append(f_edit)

        # Col 11: ⚙️ Gear Rule Configuration Button
        btn_gear = QPushButton(f"⚙️  {dto.conditions_summary}")
        btn_gear.setObjectName("SheetCellGear")
        btn_gear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gear.clicked.connect(
            lambda _, b=btn_gear, r=dto: self._open_gear_dialog(b, r)
        )
        self.sheet_table.setCellWidget(row_idx, 11, btn_gear)

        # Col 12: Action Delete Button
        btn_del = QPushButton("🗑️")
        btn_del.setObjectName("SheetCellDelete")
        btn_del.setToolTip("Delete this rule row")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda _, r=dto, idx=row_idx: self._handle_delete_row(r, idx))
        self.sheet_table.setCellWidget(row_idx, 12, btn_del)

        self.sheet_table.setRowHeight(row_idx, 32)

        # Connect cascading signals
        ws_combo.currentIndexChanged.connect(
            lambda _, w=ws_combo, d=ds_combo, t=tbl_combo, c=col_combo, r=dto: self._on_row_workspace_changed(
                w, d, t, c, r
            )
        )
        ds_combo.currentIndexChanged.connect(
            lambda _, d=ds_combo, t=tbl_combo, c=col_combo, r=dto: self._on_row_dataset_changed(
                d, r, t, c
            )
        )
        tbl_combo.currentTextChanged.connect(
            lambda txt, r=dto, cc=col_combo: self._on_row_table_changed(txt, r, cc)
        )
        col_combo.currentTextChanged.connect(
            lambda txt, r=dto: self._on_row_column_measure_changed(txt, r)
        )
        test_combo.currentIndexChanged.connect(
            lambda _, tc=test_combo, ti=tbl_combo, ci=col_combo, fe=filter_edits, bg=btn_gear, r=dto: self._on_test_type_changed(
                tc, ti, ci, fe, bg, r
            )
        )
        self._apply_test_type_rules(test_combo.currentData(), tbl_combo, col_combo, filter_edits)

    # =========================================================================
    # Cascading Dropdowns & Control Handlers
    # =========================================================================

    def _connect_metadata_service(self) -> None:
        if self._metadata_service is not None:
            self._metadata_service.metadata_loaded.connect(self._on_metadata_loaded)
            self._metadata_service.metadata_failed.connect(self._on_metadata_failed)

    def _on_metadata_loaded(self, metadata: DatasetMetadata) -> None:
        """Repopulate table and column/measure dropdowns once background discovery finishes."""
        for row_idx in range(self.sheet_table.rowCount()):
            if row_idx < len(self._rows):
                dto = self._rows[row_idx]
                ws_match = (
                    not dto.workspace_id
                    or dto.workspace_id.lower() == metadata.workspace_id.lower()
                    or metadata.workspace_id == "my_workspace"
                )
                ds_match = (
                    not dto.dataset_id
                    or dto.dataset_id.lower() == metadata.dataset_id.lower()
                )
                if ws_match and ds_match:
                    tbl_combo = self.sheet_table.cellWidget(row_idx, 5)
                    col_combo = self.sheet_table.cellWidget(row_idx, 6)
                    if isinstance(tbl_combo, EditableCellCombo):
                        self._populate_table_combo(
                            tbl_combo,
                            workspace_id=dto.workspace_id,
                            dataset_id=dto.dataset_id,
                            selected_tbl=dto.table_name or tbl_combo.text(),
                        )
                    if isinstance(col_combo, EditableCellCombo):
                        self._populate_column_measure_combo(
                            col_combo,
                            workspace_id=dto.workspace_id,
                            dataset_id=dto.dataset_id,
                            table_name=dto.table_name or (tbl_combo.text() if isinstance(tbl_combo, EditableCellCombo) else None),
                            selected_val=dto.measure_name or dto.column_name or col_combo.text(),
                            validation_type=dto.validation_type,
                        )

    def _on_metadata_failed(self, dataset_id: str, error_msg: str) -> None:
        logger.debug("Metadata discovery notice for dataset %s: %s", dataset_id, error_msg)

    def _populate_table_combo(
        self,
        combo: EditableCellCombo,
        *,
        workspace_id: str,
        dataset_id: str,
        selected_tbl: str | None = None,
    ) -> None:
        combo.blockSignals(True)
        current_val = selected_tbl if selected_tbl is not None else combo.text()
        combo.clear()

        table_names: list[str] = []
        if self._metadata_service is not None and dataset_id:
            meta = self._metadata_service.get_cached_metadata(workspace_id, dataset_id)
            if meta is not None and meta.table_names:
                table_names = list(meta.table_names)
            elif not meta and not self._metadata_service.is_busy:
                self._metadata_service.fetch_metadata_async(workspace_id, dataset_id)

        for tbl_name in table_names:
            combo.addItem(tbl_name, tbl_name)

        if current_val:
            idx = combo.findText(current_val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentIndex(-1)
                combo.setEditText(current_val)
        else:
            combo.setCurrentIndex(-1)
            combo.setEditText("")

        combo.setPlaceholderText("Table, e.g. Sales")
        combo.blockSignals(False)

    def _populate_column_measure_combo(
        self,
        combo: EditableCellCombo,
        *,
        workspace_id: str,
        dataset_id: str,
        table_name: str | None,
        selected_val: str | None = None,
        validation_type: str = VALIDATION_TYPE_NULL,
    ) -> None:
        combo.blockSignals(True)
        current_val = selected_val if selected_val is not None else combo.text()
        combo.clear()

        if validation_type == VALIDATION_TYPE_REFRESH:
            combo.setCurrentIndex(-1)
            combo.setEditText("")
            combo.setPlaceholderText("— (Model SLA)")
            combo.blockSignals(False)
            return

        if validation_type == VALIDATION_TYPE_DAX_MEASURE:
            combo.setPlaceholderText("Measure, e.g. [Total Sales]")
            measure_names: list[str] = []
            if self._metadata_service is not None and dataset_id:
                meta = self._metadata_service.get_cached_metadata(workspace_id, dataset_id)
                if meta is not None and meta.measure_names:
                    measure_names = list(meta.measure_names)
                elif not meta and not self._metadata_service.is_busy:
                    self._metadata_service.fetch_metadata_async(workspace_id, dataset_id)

            for m in measure_names:
                display = f"[{m}]"
                combo.addItem(display, m)

            if current_val:
                bare = current_val.strip("[]")
                bracketed = f"[{bare}]"
                idx = combo.findText(bracketed)
                if idx < 0:
                    idx = combo.findText(bare)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setCurrentIndex(-1)
                    combo.setEditText(current_val)
            else:
                combo.setCurrentIndex(-1)
                combo.setEditText("")
        else:
            combo.setPlaceholderText("Column, e.g. Amount")
            column_names: list[str] = []
            if self._metadata_service is not None and dataset_id and table_name:
                meta = self._metadata_service.get_cached_metadata(workspace_id, dataset_id)
                if meta is not None:
                    tbl = meta.get_table(table_name)
                    if tbl is not None and tbl.column_names:
                        column_names = list(tbl.column_names)
                elif not meta and not self._metadata_service.is_busy:
                    self._metadata_service.fetch_metadata_async(workspace_id, dataset_id)

            for col in column_names:
                combo.addItem(col, col)

            if current_val:
                idx = combo.findText(current_val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setCurrentIndex(-1)
                    combo.setEditText(current_val)
            else:
                combo.setCurrentIndex(-1)
                combo.setEditText("")

        combo.blockSignals(False)

    def _on_row_enabled_changed(self, state: bool, dto: SheetRowDTO) -> None:
        dto.enabled = state
        self._mark_dirty()
        self._update_stats_label()

    def _populate_workspace_combo(
        self,
        combo: QComboBox,
        *,
        selected_id: str = "",
        selected_name: str = "",
    ) -> None:
        combo.blockSignals(True)
        combo.clear()

        # Collect options from cached Power BI workspaces or registered registrations
        options: list[tuple[str, str]] = []  # (name, id)

        workspaces_source = list(self._cached_workspaces)
        if not workspaces_source and self._powerbi_service is not None:
            workspaces_source = self._powerbi_service.cached_workspaces
            if workspaces_source:
                self._cached_workspaces = list(workspaces_source)

        for ws in workspaces_source:
            if not any(opt[1].lower() == ws.id.lower() for opt in options):
                options.append((ws.name, ws.id))

        if self._registry_service is not None:
            regs = self._registry_service.list_registrations(active_only=False)
            for reg in regs:
                if not any(opt[1].lower() == reg.workspace_id.lower() for opt in options):
                    options.append((reg.workspace_name, reg.workspace_id))

        if selected_id and not any(opt[1].lower() == selected_id.lower() for opt in options):
            options.append((selected_name or f"Workspace {selected_id[:8]}", selected_id))

        if not options:
            options.append(("No workspaces loaded (Click 'Sync Power BI')", ""))

        select_idx = 0
        for idx, (name, ws_id) in enumerate(options):
            label = f"{name} ({ws_id[:8]}...)" if ws_id else name
            combo.addItem(label, ws_id)
            if selected_id and ws_id.lower() == selected_id.lower():
                select_idx = idx

        combo.setCurrentIndex(select_idx)
        combo.blockSignals(False)

    def _populate_dataset_combo(
        self,
        combo: QComboBox,
        *,
        workspace_id: str,
        selected_ds_id: str = "",
        selected_report_name: str = "",
    ) -> None:
        combo.blockSignals(True)
        combo.clear()

        options: list[tuple[str, str, str]] = []  # (report_name, dataset_id, report_id)
        ws_key = workspace_id.lower() if workspace_id else ""

        # Check cached assets for this workspace
        if ws_key and ws_key in self._cached_assets:
            datasets, reports = self._cached_assets[ws_key]
            for ds in datasets:
                matching_rpt = next((r for r in reports if (r.dataset_id or "").lower() == ds.id.lower()), None)
                rpt_title = matching_rpt.name if matching_rpt else ds.name
                rpt_id = matching_rpt.id if matching_rpt else ""
                options.append((rpt_title, ds.id, rpt_id))
        elif ws_key and self._powerbi_service is not None:
            datasets = self._powerbi_service.get_cached_datasets(workspace_id)
            reports = self._powerbi_service.get_cached_reports(workspace_id)
            if datasets or reports:
                self._cached_assets[ws_key] = (list(datasets), list(reports))
                for ds in datasets:
                    matching_rpt = next((r for r in reports if (r.dataset_id or "").lower() == ds.id.lower()), None)
                    rpt_title = matching_rpt.name if matching_rpt else ds.name
                    rpt_id = matching_rpt.id if matching_rpt else ""
                    options.append((rpt_title, ds.id, rpt_id))

        # Also check registrations in SQLite
        if self._registry_service is not None:
            regs = self._registry_service.list_registrations(active_only=False)
            for reg in regs:
                if not workspace_id or reg.workspace_id.lower() == workspace_id.lower():
                    if not any(opt[1].lower() == reg.dataset_id.lower() for opt in options):
                        options.append((reg.report_name, reg.dataset_id, reg.report_id or ""))

        if selected_ds_id and not any(opt[1].lower() == selected_ds_id.lower() for opt in options):
            options.append((selected_report_name or f"Dataset {selected_ds_id[:8]}", selected_ds_id, ""))

        if not options:
            options.append(("No reports found for this workspace", "", ""))

        select_idx = 0
        for idx, (rpt_name, ds_id, rpt_id) in enumerate(options):
            label = f"{rpt_name} ({ds_id[:8]}...)" if ds_id else rpt_name
            combo.addItem(label, (ds_id, rpt_name, rpt_id))
            if selected_ds_id and ds_id.lower() == selected_ds_id.lower():
                select_idx = idx

        combo.setCurrentIndex(select_idx)
        combo.blockSignals(False)

    def _on_row_workspace_changed(
        self,
        ws_combo: QComboBox,
        ds_combo: QComboBox,
        tbl_combo: EditableCellCombo,
        col_combo: EditableCellCombo,
        dto: SheetRowDTO,
    ) -> None:
        ws_id = str(ws_combo.currentData() or "")
        ws_name = ws_combo.currentText().split(" (")[0]
        if dto.workspace_id != ws_id:
            dto.workspace_id = ws_id
            dto.workspace_name = ws_name
            self._mark_dirty()

            # Cascade update dataset dropdown
            self._populate_dataset_combo(ds_combo, workspace_id=ws_id)
            self._on_row_dataset_changed(ds_combo, dto, tbl_combo, col_combo)

            # Trigger async fetch if assets not yet cached
            ws_key = ws_id.lower() if ws_id else ""
            if ws_key and ws_key not in self._cached_assets and self._powerbi_service is not None:
                self._powerbi_service.list_workspace_assets_async(ws_id)

    def _on_row_dataset_changed(
        self,
        ds_combo: QComboBox,
        dto: SheetRowDTO,
        tbl_combo: EditableCellCombo | None = None,
        col_combo: EditableCellCombo | None = None,
    ) -> None:
        data = ds_combo.currentData()
        if isinstance(data, tuple) and len(data) >= 3:
            ds_id, rpt_name, rpt_id = data
            if dto.dataset_id != ds_id:
                dto.dataset_id = ds_id
                dto.report_name = rpt_name
                dto.dataset_name = rpt_name
                dto.report_id = rpt_id or None
                self._mark_dirty()

                # Refresh table & column combos for this row if provided
                if tbl_combo is not None:
                    self._populate_table_combo(
                        tbl_combo,
                        workspace_id=dto.workspace_id,
                        dataset_id=dto.dataset_id,
                        selected_tbl="",
                    )
                if col_combo is not None:
                    self._populate_column_measure_combo(
                        col_combo,
                        workspace_id=dto.workspace_id,
                        dataset_id=dto.dataset_id,
                        table_name=dto.table_name,
                        selected_val="",
                        validation_type=dto.validation_type,
                    )

                # Trigger async fetch if metadata not yet cached
                if self._metadata_service is not None and dto.workspace_id and dto.dataset_id:
                    meta = self._metadata_service.get_cached_metadata(dto.workspace_id, dto.dataset_id)
                    if meta is None and not self._metadata_service.is_busy:
                        self._metadata_service.fetch_metadata_async(dto.workspace_id, dto.dataset_id)

    def _on_row_table_changed(
        self,
        txt: str,
        dto: SheetRowDTO,
        col_combo: EditableCellCombo,
    ) -> None:
        tbl_name = txt.strip() or None
        if dto.table_name != tbl_name:
            dto.table_name = tbl_name
            self._mark_dirty()
            # Cascade into column combo
            self._populate_column_measure_combo(
                col_combo,
                workspace_id=dto.workspace_id,
                dataset_id=dto.dataset_id,
                table_name=tbl_name,
                selected_val=col_combo.text(),
                validation_type=dto.validation_type,
            )

    def _on_row_column_measure_changed(self, txt: str, dto: SheetRowDTO) -> None:
        old_col = dto.column_name
        old_meas = dto.measure_name
        self._on_col_measure_changed(txt, dto)
        if dto.column_name != old_col or dto.measure_name != old_meas:
            self._mark_dirty()

    def _on_row_filter_changed(self, txt: str, dto: SheetRowDTO, prop_name: str) -> None:
        clean = txt.strip()
        setattr(dto, prop_name, clean)
        if clean:
            dto.config[prop_name] = clean
        else:
            dto.config.pop(prop_name, None)
        self._mark_dirty()

    def _on_col_measure_changed(self, txt: str, dto: SheetRowDTO) -> None:
        raw = txt.strip()
        if dto.validation_type == VALIDATION_TYPE_DAX_MEASURE or (raw.startswith("[") and raw.endswith("]")):
            dto.measure_name = raw.strip("[]")
            dto.column_name = None
        else:
            dto.column_name = raw or None
            dto.measure_name = None

    def _on_test_type_changed(
        self,
        test_combo: QComboBox,
        tbl_combo: QWidget,
        col_combo: QWidget,
        filter_edits: list[QLineEdit] | None,
        btn_gear: QPushButton,
        dto: SheetRowDTO,
    ) -> None:
        new_vtype = str(test_combo.currentData() or VALIDATION_TYPE_NULL)
        if dto.validation_type != new_vtype:
            dto.validation_type = new_vtype
            self._mark_dirty()

            self._apply_test_type_rules(new_vtype, tbl_combo, col_combo, filter_edits)

            if isinstance(col_combo, EditableCellCombo):
                self._populate_column_measure_combo(
                    col_combo,
                    workspace_id=dto.workspace_id,
                    dataset_id=dto.dataset_id,
                    table_name=dto.table_name,
                    selected_val=dto.measure_name or dto.column_name or col_combo.text(),
                    validation_type=new_vtype,
                )

            # Provide friendly default config if type was switched
            if new_vtype == VALIDATION_TYPE_REFRESH and "expected_status" not in dto.config:
                dto.config = {"expected_status": "Completed", "max_age_hours": 24}
            elif new_vtype == VALIDATION_TYPE_NULL and "allowed_blank_count" not in dto.config:
                dto.config = {"allowed_blank_count": 0, "include_empty_string": True}
            elif new_vtype == VALIDATION_TYPE_DUPLICATE and "allowed_duplicate_count" not in dto.config:
                dto.config = {"allowed_duplicate_count": 0}

            btn_gear.setText(f"⚙️  {dto.conditions_summary}")

    def _apply_test_type_rules(
        self,
        vtype: str,
        tbl_input: QWidget,
        col_input: QWidget,
        filter_edits: list[QLineEdit] | None = None,
    ) -> None:
        if vtype == VALIDATION_TYPE_REFRESH:
            tbl_input.setEnabled(False)
            if hasattr(tbl_input, "setPlaceholderText"):
                tbl_input.setPlaceholderText("— (Model SLA)")
            col_input.setEnabled(False)
            if hasattr(col_input, "setPlaceholderText"):
                col_input.setPlaceholderText("— (Model SLA)")
            if filter_edits:
                for fe in filter_edits:
                    fe.setEnabled(False)
                    fe.setPlaceholderText("— (N/A)")
        elif vtype == VALIDATION_TYPE_DAX_MEASURE:
            tbl_input.setEnabled(False)
            if hasattr(tbl_input, "setPlaceholderText"):
                tbl_input.setPlaceholderText("— (DAX Measure)")
            col_input.setEnabled(True)
            if hasattr(col_input, "setPlaceholderText"):
                col_input.setPlaceholderText("Measure, e.g. [Sales]")
            if filter_edits:
                for idx, fe in enumerate(filter_edits, start=1):
                    fe.setEnabled(True)
                    fe.setPlaceholderText(f"Filter {idx} (e.g. 'Dates'[Year]=2024)")
        else:
            tbl_input.setEnabled(True)
            if hasattr(tbl_input, "setPlaceholderText"):
                tbl_input.setPlaceholderText("Table, e.g. Sales")
            col_input.setEnabled(True)
            if hasattr(col_input, "setPlaceholderText"):
                col_input.setPlaceholderText("Column, e.g. Amount")
            if filter_edits:
                for idx, fe in enumerate(filter_edits, start=1):
                    fe.setEnabled(True)
                    fe.setPlaceholderText(f"Filter {idx} (e.g. 'Dates'[Year]=2024)")

    def _open_gear_dialog(self, btn_gear: QPushButton, dto: SheetRowDTO) -> None:
        dialog = SheetRuleConfigDialog(
            validation_type=dto.validation_type,
            target_display=dto.target_display,
            current_config=dto.config,
            rule_name=dto.rule_name or "",
            parent=self,
        )
        if dialog.exec():
            dto.config = dialog.config
            if dialog.rule_name:
                dto.rule_name = dialog.rule_name
            btn_gear.setText(f"⚙️  {dto.conditions_summary}")
            self._mark_dirty()
            self.banner.show_message(
                f"Updated conditions for row #{dto.sr_no}: {dto.conditions_summary}",
                level=NotificationLevel.INFO,
                title="Condition Configured",
            )

    # =========================================================================
    # Ribbon Actions: Add, Delete, Save, Sync, Import, Export
    # =========================================================================

    def _handle_add_row(self) -> None:
        # Resolve sensible defaults from cached workspaces or registrations
        def_ws_id = ""
        def_ws_name = ""
        def_ds_id = ""
        def_rpt_name = ""

        workspaces_source = list(self._cached_workspaces)
        if not workspaces_source and self._powerbi_service is not None:
            workspaces_source = self._powerbi_service.cached_workspaces

        if workspaces_source:
            def_ws_id = workspaces_source[0].id
            def_ws_name = workspaces_source[0].name
            ws_key = def_ws_id.lower()
            if ws_key in self._cached_assets:
                datasets, _ = self._cached_assets[ws_key]
                if datasets:
                    def_ds_id = datasets[0].id
                    def_rpt_name = datasets[0].name
            elif self._powerbi_service is not None:
                datasets = self._powerbi_service.get_cached_datasets(def_ws_id)
                if datasets:
                    def_ds_id = datasets[0].id
                    def_rpt_name = datasets[0].name

        if not def_ws_id and self._registry_service is not None:
            regs = self._registry_service.list_registrations(active_only=True)
            if regs:
                def_ws_id = regs[0].workspace_id
                def_ws_name = regs[0].workspace_name
                def_ds_id = regs[0].dataset_id
                def_rpt_name = regs[0].report_name

        new_dto = SheetRowDTO(
            row_id=None,
            sr_no=len(self._rows) + 1,
            enabled=True,
            workspace_id=def_ws_id,
            workspace_name=def_ws_name,
            dataset_id=def_ds_id,
            report_name=def_rpt_name,
            validation_type=VALIDATION_TYPE_NULL,
            table_name="",
            column_name="",
            config={"allowed_blank_count": 0},
        )
        self._rows.append(new_dto)

        new_row_idx = self.sheet_table.rowCount()
        self.sheet_table.insertRow(new_row_idx)
        self._render_row_cells(new_row_idx, new_dto)
        self.sheet_table.scrollToBottom()
        self._update_stats_label()
        self._mark_dirty()

        self.banner.show_message(
            f"Added new validation row #{new_row_idx + 1}. Configure your test and click 'Save Sheet'.",
            level=NotificationLevel.INFO,
            title="Row Added",
        )

    def _handle_delete_selected_row(self) -> None:
        selected_indexes = self.sheet_table.selectionModel().selectedRows()
        if not selected_indexes:
            self.banner.show_message(
                "Please click a row in the sheet to select it first, then click Delete Row.",
                level=NotificationLevel.WARNING,
                title="No Row Selected",
            )
            return

        row_idx = selected_indexes[0].row()
        if 0 <= row_idx < len(self._rows):
            dto = self._rows[row_idx]
            self._handle_delete_row(dto, row_idx)

    def _handle_delete_row(self, dto: SheetRowDTO, row_idx: int) -> None:
        if dto.row_id is not None and self._sheet_service is not None:
            try:
                self._sheet_service.delete_sheet_row(dto.row_id)
            except Exception as exc:
                self.banner.show_message(
                    f"Could not delete rule from database: {format_safe_user_error(exc)}",
                    level=NotificationLevel.ERROR,
                    title="Delete Failed",
                )
                return

        if dto in self._rows:
            self._rows.remove(dto)

        self.sheet_table.removeRow(row_idx)
        self._renumber_sr_column()
        self._update_stats_label()
        self._mark_dirty()

        self.banner.show_message(
            "Row removed from validation sheet.",
            level=NotificationLevel.INFO,
            title="Row Deleted",
        )

    def _renumber_sr_column(self) -> None:
        for idx in range(self.sheet_table.rowCount()):
            item = self.sheet_table.item(idx, 0)
            if item is not None:
                item.setText(str(idx + 1))
            if idx < len(self._rows):
                self._rows[idx].sr_no = idx + 1

    def _sync_widgets_to_rows(self) -> None:
        """Sync values from table cell widgets into in-memory DTOs."""
        for idx in range(self.sheet_table.rowCount()):
            if idx < len(self._rows):
                r = self._rows[idx]
                ws_combo = self.sheet_table.cellWidget(idx, 2)
                ds_combo = self.sheet_table.cellWidget(idx, 3)
                tbl_input = self.sheet_table.cellWidget(idx, 5)
                col_input = self.sheet_table.cellWidget(idx, 6)

                if isinstance(ws_combo, QComboBox) and ws_combo.currentData():
                    r.workspace_id = str(ws_combo.currentData())
                    r.workspace_name = ws_combo.currentText().split(" (")[0]
                if isinstance(ds_combo, QComboBox) and ds_combo.currentData():
                    d_data = ds_combo.currentData()
                    if isinstance(d_data, tuple) and len(d_data) >= 3:
                        r.dataset_id = d_data[0]
                        r.report_name = d_data[1]
                        r.dataset_name = d_data[1]
                        r.report_id = d_data[2] or None
                if isinstance(tbl_input, (QLineEdit, QComboBox)):
                    tbl_val = (
                        tbl_input.currentText().strip()
                        if isinstance(tbl_input, QComboBox)
                        else tbl_input.text().strip()
                    )
                    r.table_name = tbl_val or None
                if isinstance(col_input, (QLineEdit, QComboBox)):
                    col_val = (
                        col_input.currentText().strip()
                        if isinstance(col_input, QComboBox)
                        else col_input.text().strip()
                    )
                    self._on_col_measure_changed(col_val, r)

    def _handle_auto_save(self) -> None:
        """Periodic background auto-save (runs every 1 minute) to persist changes safely."""
        if not self._is_dirty or not self._rows or self._sheet_service is None:
            return

        self._sync_widgets_to_rows()

        # Check if rows are configured enough to be persisted
        for r in self._rows:
            if not r.workspace_id or not r.dataset_id:
                return
            if r.validation_type != VALIDATION_TYPE_REFRESH:
                if r.validation_type == VALIDATION_TYPE_DAX_MEASURE and not r.measure_name:
                    return
                elif r.validation_type != VALIDATION_TYPE_DAX_MEASURE and not r.table_name:
                    return
                if r.validation_type in (VALIDATION_TYPE_NULL, VALIDATION_TYPE_DUPLICATE, VALIDATION_TYPE_LATEST_DATE) and not r.column_name:
                    return

        try:
            saved_rows = self._sheet_service.save_all_rows(self._rows)
            for idx, s_row in enumerate(saved_rows):
                if idx < len(self._rows):
                    self._rows[idx].row_id = s_row.row_id
            self._mark_clean(f"✓ Auto-saved at {datetime.now().strftime('%H:%M:%S')}")
            logger.info("Auto-saved %d sheet row(s) successfully.", len(saved_rows))
        except Exception as exc:
            logger.warning("Auto-save attempt skipped due to error: %s", exc)

    def _handle_save_sheet(self) -> None:
        if self._sheet_service is None:
            self.banner.show_message(
                "Sheet storage service is not initialized.",
                level=NotificationLevel.ERROR,
                title="Service Error",
            )
            return

        if not self._rows:
            self.banner.show_message(
                "The sheet is currently empty. Click '➕ Add Row' to define your first test.",
                level=NotificationLevel.WARNING,
                title="Empty Sheet",
            )
            return

        self._sync_widgets_to_rows()

        # Validate rows before saving
        for idx, r in enumerate(self._rows, start=1):
            if not r.workspace_id or not r.dataset_id:
                self.banner.show_message(
                    f"Row #{idx}: Workspace and Report / Dataset must be selected.",
                    level=NotificationLevel.ERROR,
                    title="Validation Error",
                )
                return
            if r.validation_type != VALIDATION_TYPE_REFRESH:
                if r.validation_type == VALIDATION_TYPE_DAX_MEASURE and not r.measure_name:
                    self.banner.show_message(
                        f"Row #{idx}: DAX Measure Check requires a Measure Name in the 'Column or Measure' column.",
                        level=NotificationLevel.ERROR,
                        title="Validation Error",
                    )
                    return
                elif r.validation_type != VALIDATION_TYPE_DAX_MEASURE:
                    if not r.table_name:
                        self.banner.show_message(
                            f"Row #{idx}: {r.validation_type_display} requires a Table Name.",
                            level=NotificationLevel.ERROR,
                            title="Validation Error",
                        )
                        return
                    if r.validation_type in (VALIDATION_TYPE_NULL, VALIDATION_TYPE_DUPLICATE, VALIDATION_TYPE_LATEST_DATE) and not r.column_name:
                        self.banner.show_message(
                            f"Row #{idx}: {r.validation_type_display} requires a Column Name.",
                            level=NotificationLevel.ERROR,
                            title="Validation Error",
                        )
                        return

        try:
            self.btn_save_sheet.setEnabled(False)
            self.btn_save_sheet.setText("Saving...")
            saved_rows = self._sheet_service.save_all_rows(self._rows)
            self._rows = saved_rows
            self.reload_sheet()
            self._mark_clean()
            self.banner.show_message(
                f"Successfully saved {len(saved_rows)} validation test row(s) to Power BI tool database!",
                level=NotificationLevel.SUCCESS,
                title="Sheet Saved",
            )
        except Exception as exc:
            logger.exception("Failed to save validation sheet: %s", exc)
            self.banner.show_message(
                f"Failed to save sheet: {format_safe_user_error(exc)}",
                level=NotificationLevel.ERROR,
                title="Save Error",
            )
        finally:
            self.btn_save_sheet.setEnabled(True)
            self.btn_save_sheet.setText("💾  Save Sheet")

    def _handle_sync_powerbi(self) -> None:
        self.sync_workspaces_requested.emit()
        if self._powerbi_service is not None:
            self.btn_sync_pbi.setEnabled(False)
            self.btn_sync_pbi.setText("Syncing...")
            self.banner.show_message(
                "Connecting to Power BI service to fetch accessible workspaces and datasets...",
                level=NotificationLevel.INFO,
                title="Sync in Progress",
            )
            if not self._powerbi_service.is_busy:
                self._powerbi_service.sync_all_workspaces_and_assets_async()
        else:
            self.banner.show_message(
                "Power BI service is not configured. Please sign in via the top authentication banner.",
                level=NotificationLevel.WARNING,
                title="Authentication Needed",
            )

    def _connect_powerbi_service(self) -> None:
        if self._powerbi_service is not None:
            self._powerbi_service.workspaces_loaded.connect(self._on_workspaces_loaded)
            self._powerbi_service.workspace_assets_loaded.connect(self._on_workspace_assets_loaded)
            self._powerbi_service.error_occurred.connect(self._on_powerbi_error)

    def _on_workspaces_loaded(self, workspaces: list[PowerBIWorkspace]) -> None:
        self.btn_sync_pbi.setEnabled(True)
        self.btn_sync_pbi.setText("🔄 Sync PBI")
        self._cached_workspaces = list(workspaces)

        # Refresh all workspace combos across existing rows
        for row_idx in range(self.sheet_table.rowCount()):
            ws_combo = self.sheet_table.cellWidget(row_idx, 2)
            if isinstance(ws_combo, QComboBox) and row_idx < len(self._rows):
                dto = self._rows[row_idx]
                self._populate_workspace_combo(ws_combo, selected_id=dto.workspace_id, selected_name=dto.workspace_name)

        self.banner.show_message(
            f"Successfully synced {len(workspaces)} Power BI workspace(s). Dropdowns are now updated.",
            level=NotificationLevel.SUCCESS,
            title="Workspaces Synced",
        )

    def _on_workspace_assets_loaded(
        self,
        workspace_id: str,
        datasets: list[PowerBIDataset],
        reports: list[PowerBIReport],
    ) -> None:
        self._cached_assets[workspace_id.lower()] = (list(datasets), list(reports))

        # Update dataset combos for rows targeting this workspace
        for row_idx in range(self.sheet_table.rowCount()):
            if row_idx < len(self._rows) and self._rows[row_idx].workspace_id.lower() == workspace_id.lower():
                ds_combo = self.sheet_table.cellWidget(row_idx, 3)
                if isinstance(ds_combo, QComboBox):
                    self._populate_dataset_combo(
                        ds_combo,
                        workspace_id=workspace_id,
                        selected_ds_id=self._rows[row_idx].dataset_id,
                        selected_report_name=self._rows[row_idx].report_name,
                    )

    def _on_powerbi_error(self, err_msg: str) -> None:
        self.btn_sync_pbi.setEnabled(True)
        self.btn_sync_pbi.setText("🔄 Sync PBI")
        self.banner.show_message(
            f"Power BI sync encountered an issue: {err_msg}",
            level=NotificationLevel.WARNING,
            title="Sync Issue",
        )

    # =========================================================================
    # File Import & Export
    # =========================================================================

    def _handle_export_sheet(self) -> None:
        if not self._rows:
            self.banner.show_message(
                "No rows to export. Add rows to the sheet first.",
                level=NotificationLevel.WARNING,
                title="Export Warning",
            )
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Validation Sheet",
            "PowerBI_Validation_Sheet.xlsx",
            "Excel Workbook (*.xlsx);;CSV File (*.csv)",
        )
        if not file_path:
            return

        try:
            if file_path.endswith(".csv") or "CSV" in selected_filter:
                self._export_to_csv(Path(file_path))
            else:
                self._export_to_xlsx(Path(file_path))

            self.banner.show_message(
                f"Exported {len(self._rows)} validation test row(s) to: {file_path}",
                level=NotificationLevel.SUCCESS,
                title="Export Complete",
            )
        except Exception as exc:
            logger.exception("Failed to export sheet: %s", exc)
            self.banner.show_message(
                f"Export failed: {format_safe_user_error(exc)}",
                level=NotificationLevel.ERROR,
                title="Export Error",
            )

    def _export_to_csv(self, dest: Path) -> None:
        with open(dest, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Sr",
                "Enabled",
                "Workspace Name",
                "Workspace ID",
                "Report Name",
                "Dataset ID",
                "Test to Do",
                "Table Name",
                "Column or Measure",
                "Filter 1",
                "Filter 2",
                "Filter 3",
                "Filter 4",
                "Conditions Summary",
            ])
            for r in self._rows:
                writer.writerow([
                    r.sr_no,
                    "TRUE" if r.enabled else "FALSE",
                    r.workspace_name,
                    r.workspace_id,
                    r.report_name,
                    r.dataset_id,
                    r.validation_type_display,
                    r.table_name or "",
                    r.measure_name or r.column_name or "",
                    r.filter_1 or "",
                    r.filter_2 or "",
                    r.filter_3 or "",
                    r.filter_4 or "",
                    r.conditions_summary,
                ])

    def _export_to_xlsx(self, dest: Path) -> None:
        import openpyxl
        from openpyxl.styles import Font, PatternFill

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Validation Sheet"

        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1668DC", end_color="1668DC", fill_type="solid")

        headers = [
            "Sr",
            "Enabled",
            "Workspace Name",
            "Workspace ID",
            "Report Name",
            "Dataset ID",
            "Test to Do",
            "Table Name",
            "Column or Measure",
            "Filter 1",
            "Filter 2",
            "Filter 3",
            "Filter 4",
            "Conditions Summary",
        ]
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill

        for r in self._rows:
            ws.append([
                r.sr_no,
                "TRUE" if r.enabled else "FALSE",
                r.workspace_name,
                r.workspace_id,
                r.report_name,
                r.dataset_id,
                r.validation_type_display,
                r.table_name or "",
                r.measure_name or r.column_name or "",
                r.filter_1 or "",
                r.filter_2 or "",
                r.filter_3 or "",
                r.filter_4 or "",
                r.conditions_summary,
            ])

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        wb.save(dest)

    def _handle_import_sheet(self) -> None:
        from app.ui.dialogs.import_sheet_dialog import ImportSheetDialog

        dialog = ImportSheetDialog(sheet_service=self._sheet_service, parent=self)
        if not dialog.exec():
            return

        imported = dialog.imported_rows
        if not imported:
            return

        if dialog.replace_mode:
            self._rows = imported
        else:
            self._rows.extend(imported)

        self._handle_save_sheet()
        self.banner.show_message(
            f"Successfully imported {len(imported)} validation test(s)!",
            level=NotificationLevel.SUCCESS,
            title="Import Successful",
        )

    def _parse_import_file(self, path: Path) -> list[SheetRowDTO]:
        rows: list[SheetRowDTO] = []
        if path.suffix.lower() == ".csv":
            with open(path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for item in reader:
                    dto = self._dict_to_row_dto(item)
                    if dto:
                        rows.append(dto)
        else:
            import openpyxl

            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb.active
            headers = [str(c or "").strip() for c in next(ws.iter_rows(values_only=True))]
            for row_vals in ws.iter_rows(min_row=2, values_only=True):
                item = {headers[i]: row_vals[i] for i in range(min(len(headers), len(row_vals)))}
                dto = self._dict_to_row_dto(item)
                if dto:
                    rows.append(dto)
        return rows

    def _dict_to_row_dto(self, item: dict[str, Any]) -> SheetRowDTO | None:
        ws_id = str(item.get("Workspace ID", "") or "").strip()
        ds_id = str(item.get("Dataset ID", "") or "").strip()
        if not ws_id or not ds_id:
            return None

        test_str = str(item.get("Test to Do", "") or "").strip().lower()
        vtype = TEST_NAME_TO_TYPE.get(test_str, VALIDATION_TYPE_NULL)

        target = str(item.get("Column or Measure", "") or "").strip()
        is_measure = vtype == VALIDATION_TYPE_DAX_MEASURE or (target.startswith("[") and target.endswith("]"))

        f1 = str(item.get("Filter 1", "") or "").strip()
        f2 = str(item.get("Filter 2", "") or "").strip()
        f3 = str(item.get("Filter 3", "") or "").strip()
        f4 = str(item.get("Filter 4", "") or "").strip()
        cfg: dict[str, Any] = {}
        if f1:
            cfg["filter_1"] = f1
        if f2:
            cfg["filter_2"] = f2
        if f3:
            cfg["filter_3"] = f3
        if f4:
            cfg["filter_4"] = f4

        return SheetRowDTO(
            sr_no=len(self._rows) + 1,
            enabled=str(item.get("Enabled", "TRUE")).strip().upper() != "FALSE",
            workspace_name=str(item.get("Workspace Name", "") or f"Workspace {ws_id[:8]}").strip(),
            workspace_id=ws_id,
            report_name=str(item.get("Report Name", "") or f"Dataset {ds_id[:8]}").strip(),
            dataset_name=str(item.get("Report Name", "") or f"Dataset {ds_id[:8]}").strip(),
            dataset_id=ds_id,
            validation_type=vtype,
            table_name=str(item.get("Table Name", "") or "").strip() or None,
            column_name=None if is_measure else (target or None),
            measure_name=target.strip("[]") if is_measure else None,
            filter_1=f1,
            filter_2=f2,
            filter_3=f3,
            filter_4=f4,
            config=cfg,
        )

    # =========================================================================
    # Quick Filter & Stats
    # =========================================================================

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        for row_idx in range(self.sheet_table.rowCount()):
            if not q:
                self.sheet_table.setRowHidden(row_idx, False)
                continue

            if row_idx >= len(self._rows):
                continue

            r = self._rows[row_idx]
            blob = f"{r.workspace_name} {r.report_name} {r.validation_type_display} {r.table_name} {r.column_name} {r.measure_name} {r.filter_1} {r.filter_2} {r.filter_3} {r.filter_4} {r.conditions_summary}".lower()
            self.sheet_table.setRowHidden(row_idx, q not in blob)

    def _update_stats_label(self) -> None:
        total = len(self._rows)
        enabled = sum(1 for r in self._rows if r.enabled)
        unique_ws = len(set(r.workspace_id for r in self._rows if r.workspace_id))
        self.lbl_row_stats.setText(
            f"Total Rows: {total}  |  Enabled: {enabled}  |  Workspaces: {unique_ws}"
        )
