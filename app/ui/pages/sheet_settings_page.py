"""Excel-style validation settings page with menu ribbon and sheet table (Stage D).

Designed for non-technical users to configure validation rules in a clean,
spreadsheet-like view with intuitive menus, cascading dropdowns, and popup
gear configuration.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
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
from app.integrations.powerbi.models import PowerBIDataset, PowerBIReport, PowerBIWorkspace
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
from app.ui.widgets.notification_banner import NotificationBanner

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

        self._cached_workspaces: list[PowerBIWorkspace] = []
        self._cached_assets: dict[str, tuple[list[PowerBIDataset], list[PowerBIReport]]] = {}
        self._rows: list[SheetRowDTO] = []
        self._is_dirty: bool = False

        self._init_ui()
        self._connect_powerbi_service()
        self.reload_sheet()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload_sheet()

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
            "border-radius: 8px; padding: 6px 12px; }"
        )
        ribbon_layout = QHBoxLayout(ribbon)
        ribbon_layout.setContentsMargins(8, 6, 8, 6)
        ribbon_layout.setSpacing(10)

        # Group 1: Sheet Actions
        self.btn_add_row = QPushButton("➕  Add Row")
        self.btn_add_row.setObjectName("PrimaryButton")
        self.btn_add_row.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 6px 14px; border-radius: 6px;"
        )
        self.btn_add_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_row.clicked.connect(self._handle_add_row)
        ribbon_layout.addWidget(self.btn_add_row)

        self.btn_delete_row = QPushButton("🗑️  Delete Row")
        self.btn_delete_row.setObjectName("SecondaryButton")
        self.btn_delete_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_row.clicked.connect(self._handle_delete_selected_row)
        ribbon_layout.addWidget(self.btn_delete_row)

        self.btn_save_sheet = QPushButton("💾  Save Sheet")
        self.btn_save_sheet.setObjectName("PrimaryButton")
        self.btn_save_sheet.setStyleSheet(
            "background-color: #10B981; color: #FFFFFF; font-weight: 700; padding: 6px 16px; border-radius: 6px;"
        )
        self.btn_save_sheet.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_sheet.clicked.connect(self._handle_save_sheet)
        ribbon_layout.addWidget(self.btn_save_sheet)

        self._add_ribbon_separator(ribbon_layout)

        # Group 2: Power BI Sync
        self.btn_sync_pbi = QPushButton("🔄  Sync Power BI")
        self.btn_sync_pbi.setObjectName("SecondaryButton")
        self.btn_sync_pbi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync_pbi.clicked.connect(self._handle_sync_powerbi)
        ribbon_layout.addWidget(self.btn_sync_pbi)

        self._add_ribbon_separator(ribbon_layout)

        # Group 3: File Transfer
        self.btn_import = QPushButton("📥  Import (Excel/CSV)")
        self.btn_import.setObjectName("SecondaryButton")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self._handle_import_sheet)
        ribbon_layout.addWidget(self.btn_import)

        self.btn_export = QPushButton("📤  Export (Excel/CSV)")
        self.btn_export.setObjectName("SecondaryButton")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._handle_export_sheet)
        ribbon_layout.addWidget(self.btn_export)

        ribbon_layout.addStretch(1)

        # Group 4: Quick Search
        self.search_filter = QLineEdit()
        self.search_filter.setObjectName("SearchInput")
        self.search_filter.setPlaceholderText("🔍  Filter sheet...")
        self.search_filter.setMinimumWidth(200)
        self.search_filter.textChanged.connect(self._apply_filter)
        ribbon_layout.addWidget(self.search_filter)

        return ribbon

    def _add_ribbon_separator(self, layout: QHBoxLayout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #E2E8F0; margin: 2px 4px;")
        layout.addWidget(sep)

    def _build_sheet_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName("DataTable")
        table.setColumnCount(9)
        table.setHorizontalHeaderLabels([
            "Sr.",
            "Enabled",
            "Workspace",
            "Report / Dataset",
            "Test to Do",
            "Table Name",
            "Column or Measure",
            "Test Rule & Settings ⚙️",
            "Action",
        ])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.resizeSection(0, 48)   # Sr.
        header.resizeSection(1, 68)   # Enabled
        header.resizeSection(2, 210)  # Workspace
        header.resizeSection(3, 230)  # Report / Dataset
        header.resizeSection(4, 190)  # Test to Do
        header.resizeSection(5, 140)  # Table Name
        header.resizeSection(6, 170)  # Column or Measure
        header.resizeSection(7, 230)  # Settings
        header.resizeSection(8, 65)   # Action

        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setStyleSheet(
            "QTableWidget { gridline-color: #E2E8F0; background: #FFFFFF; font-size: 12px; }"
            "QTableWidget::item { padding: 4px; }"
            "QHeaderView::section { background-color: #F8FAFC; color: #1E293B; font-weight: 700; "
            "border: 1px solid #CBD5E1; padding: 6px; font-size: 11px; }"
        )
        return table

    def _build_status_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(16)

        self.lbl_row_stats = QLabel("Total Rows: 0  |  Enabled: 0  |  Workspaces: 0")
        self.lbl_row_stats.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        bar.addWidget(self.lbl_row_stats)

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
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk = QCheckBox()
        chk.setChecked(dto.enabled)
        chk.toggled.connect(lambda state, r=dto: setattr(r, "enabled", state))
        chk_layout.addWidget(chk)
        self.sheet_table.setCellWidget(row_idx, 1, chk_widget)

        # Col 2: Workspace Dropdown
        ws_combo = QComboBox()
        ws_combo.setObjectName("FilterCombo")
        self._populate_workspace_combo(ws_combo, selected_id=dto.workspace_id, selected_name=dto.workspace_name)
        self.sheet_table.setCellWidget(row_idx, 2, ws_combo)

        # Col 3: Report / Dataset Dropdown
        ds_combo = QComboBox()
        ds_combo.setObjectName("FilterCombo")
        self._populate_dataset_combo(
            ds_combo,
            workspace_id=dto.workspace_id,
            selected_ds_id=dto.dataset_id,
            selected_report_name=dto.report_name,
        )
        self.sheet_table.setCellWidget(row_idx, 3, ds_combo)

        # Connect Workspace change to cascade into Report/Dataset combo
        ws_combo.currentIndexChanged.connect(
            lambda _, w=ws_combo, d=ds_combo, r=dto: self._on_row_workspace_changed(w, d, r)
        )
        ds_combo.currentIndexChanged.connect(
            lambda _, d=ds_combo, r=dto: self._on_row_dataset_changed(d, r)
        )

        # Col 4: Test to Do Dropdown
        test_combo = QComboBox()
        test_combo.setObjectName("FilterCombo")
        for key, friendly in FRIENDLY_TEST_NAMES.items():
            test_combo.addItem(friendly, key)
        # Select matching
        cur_test_idx = next(
            (i for i in range(test_combo.count()) if test_combo.itemData(i) == dto.validation_type),
            0,
        )
        test_combo.setCurrentIndex(cur_test_idx)
        self.sheet_table.setCellWidget(row_idx, 4, test_combo)

        # Col 5: Table Name input
        tbl_input = QLineEdit()
        tbl_input.setObjectName("SearchInput")
        tbl_input.setText(dto.table_name or "")
        tbl_input.setPlaceholderText("e.g. Sales")
        tbl_input.textChanged.connect(lambda txt, r=dto: setattr(r, "table_name", txt.strip() or None))
        self.sheet_table.setCellWidget(row_idx, 5, tbl_input)

        # Col 6: Column or Measure input
        col_input = QLineEdit()
        col_input.setObjectName("SearchInput")
        val = dto.measure_name if dto.measure_name else (dto.column_name or "")
        col_input.setText(val)
        col_input.setPlaceholderText("Column or [Measure]")
        col_input.textChanged.connect(
            lambda txt, r=dto: self._on_col_measure_changed(txt, r)
        )
        self.sheet_table.setCellWidget(row_idx, 6, col_input)

        # Col 7: ⚙️ Gear Rule Configuration Button
        btn_gear = QPushButton(f"⚙️  {dto.conditions_summary}")
        btn_gear.setObjectName("SecondaryButton")
        btn_gear.setStyleSheet(
            "text-align: left; padding: 4px 10px; font-size: 11px; font-weight: 600; "
            "background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 4px;"
        )
        btn_gear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gear.clicked.connect(
            lambda _, b=btn_gear, r=dto: self._open_gear_dialog(b, r)
        )
        self.sheet_table.setCellWidget(row_idx, 7, btn_gear)

        # Col 8: Action Delete Button
        btn_del = QPushButton("🗑️")
        btn_del.setObjectName("SecondaryButton")
        btn_del.setToolTip("Delete this rule row")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("padding: 3px 6px; font-size: 12px; border-radius: 4px;")
        btn_del.clicked.connect(lambda _, r=dto, idx=row_idx: self._handle_delete_row(r, idx))
        self.sheet_table.setCellWidget(row_idx, 8, btn_del)

        # Connect test combo change to toggle field states
        test_combo.currentIndexChanged.connect(
            lambda _, tc=test_combo, ti=tbl_input, ci=col_input, bg=btn_gear, r=dto: self._on_test_type_changed(
                tc, ti, ci, bg, r
            )
        )
        self._apply_test_type_rules(test_combo.currentData(), tbl_input, col_input)

    # =========================================================================
    # Cascading Dropdowns & Control Handlers
    # =========================================================================

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
        for ws in self._cached_workspaces:
            options.append((ws.name, ws.id))

        if self._registry_service is not None:
            regs = self._registry_service.list_registrations(active_only=False)
            for reg in regs:
                if not any(opt[1] == reg.workspace_id for opt in options):
                    options.append((reg.workspace_name, reg.workspace_id))

        if selected_id and not any(opt[1] == selected_id for opt in options):
            options.append((selected_name or f"Workspace {selected_id[:8]}", selected_id))

        if not options:
            options.append(("No workspaces loaded (Click 'Sync Power BI')", ""))

        select_idx = 0
        for idx, (name, ws_id) in enumerate(options):
            label = f"{name} ({ws_id[:8]}...)" if ws_id else name
            combo.addItem(label, ws_id)
            if selected_id and ws_id == selected_id:
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

        # Check cached assets for this workspace
        if workspace_id in self._cached_assets:
            datasets, reports = self._cached_assets[workspace_id]
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
                    if not any(opt[1] == reg.dataset_id for opt in options):
                        options.append((reg.report_name, reg.dataset_id, reg.report_id or ""))

        if selected_ds_id and not any(opt[1] == selected_ds_id for opt in options):
            options.append((selected_report_name or f"Dataset {selected_ds_id[:8]}", selected_ds_id, ""))

        if not options:
            options.append(("No reports found for this workspace", "", ""))

        select_idx = 0
        for idx, (rpt_name, ds_id, rpt_id) in enumerate(options):
            label = f"{rpt_name} ({ds_id[:8]}...)" if ds_id else rpt_name
            combo.addItem(label, (ds_id, rpt_name, rpt_id))
            if selected_ds_id and ds_id == selected_ds_id:
                select_idx = idx

        combo.setCurrentIndex(select_idx)
        combo.blockSignals(False)

    def _on_row_workspace_changed(self, ws_combo: QComboBox, ds_combo: QComboBox, dto: SheetRowDTO) -> None:
        ws_id = str(ws_combo.currentData() or "")
        ws_name = ws_combo.currentText().split(" (")[0]
        dto.workspace_id = ws_id
        dto.workspace_name = ws_name

        # Cascade update dataset dropdown
        self._populate_dataset_combo(ds_combo, workspace_id=ws_id)
        self._on_row_dataset_changed(ds_combo, dto)

        # Trigger async fetch if assets not yet cached
        if ws_id and ws_id not in self._cached_assets and self._powerbi_service is not None:
            self._powerbi_service.list_workspace_assets_async(ws_id)

    def _on_row_dataset_changed(self, ds_combo: QComboBox, dto: SheetRowDTO) -> None:
        data = ds_combo.currentData()
        if isinstance(data, tuple) and len(data) >= 3:
            ds_id, rpt_name, rpt_id = data
            dto.dataset_id = ds_id
            dto.report_name = rpt_name
            dto.dataset_name = rpt_name
            dto.report_id = rpt_id or None

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
        tbl_input: QLineEdit,
        col_input: QLineEdit,
        btn_gear: QPushButton,
        dto: SheetRowDTO,
    ) -> None:
        new_vtype = str(test_combo.currentData() or VALIDATION_TYPE_NULL)
        dto.validation_type = new_vtype
        self._apply_test_type_rules(new_vtype, tbl_input, col_input)

        # Provide friendly default config if type was switched
        if new_vtype == VALIDATION_TYPE_REFRESH and "expected_status" not in dto.config:
            dto.config = {"expected_status": "Completed", "max_age_hours": 24}
        elif new_vtype == VALIDATION_TYPE_NULL and "allowed_blank_count" not in dto.config:
            dto.config = {"allowed_blank_count": 0, "include_empty_string": True}
        elif new_vtype == VALIDATION_TYPE_DUPLICATE and "allowed_duplicate_count" not in dto.config:
            dto.config = {"allowed_duplicate_count": 0}

        btn_gear.setText(f"⚙️  {dto.conditions_summary}")

    def _apply_test_type_rules(self, vtype: str, tbl_input: QLineEdit, col_input: QLineEdit) -> None:
        if vtype == VALIDATION_TYPE_REFRESH:
            tbl_input.setEnabled(False)
            tbl_input.setPlaceholderText("— (Model SLA)")
            col_input.setEnabled(False)
            col_input.setPlaceholderText("— (Model SLA)")
        elif vtype == VALIDATION_TYPE_DAX_MEASURE:
            tbl_input.setEnabled(False)
            tbl_input.setPlaceholderText("— (DAX Measure)")
            col_input.setEnabled(True)
            col_input.setPlaceholderText("Measure, e.g. [Sales]")
        else:
            tbl_input.setEnabled(True)
            tbl_input.setPlaceholderText("Table, e.g. Sales")
            col_input.setEnabled(True)
            col_input.setPlaceholderText("Column, e.g. Amount")

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

        if self._cached_workspaces:
            def_ws_id = self._cached_workspaces[0].id
            def_ws_name = self._cached_workspaces[0].name
            if def_ws_id in self._cached_assets:
                datasets, _ = self._cached_assets[def_ws_id]
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

        # Sync values from table cell widgets into DTOs before saving
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
                if isinstance(tbl_input, QLineEdit):
                    r.table_name = tbl_input.text().strip() or None
                if isinstance(col_input, QLineEdit):
                    self._on_col_measure_changed(col_input.text(), r)

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
            self._powerbi_service.list_workspaces_async()
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
        self.btn_sync_pbi.setText("🔄  Sync Power BI")
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
        self._cached_assets[workspace_id] = (list(datasets), list(reports))

        # Update dataset combos for rows targeting this workspace
        for row_idx in range(self.sheet_table.rowCount()):
            if row_idx < len(self._rows) and self._rows[row_idx].workspace_id == workspace_id:
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
        self.btn_sync_pbi.setText("🔄  Sync Power BI")
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
                r.conditions_summary,
            ])

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        wb.save(dest)

    def _handle_import_sheet(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Validation Sheet",
            "",
            "Spreadsheets (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not file_path:
            return

        try:
            imported = self._parse_import_file(Path(file_path))
            if not imported:
                self.banner.show_message(
                    "No valid validation test rows found in the selected file.",
                    level=NotificationLevel.WARNING,
                    title="Import Empty",
                )
                return

            self._rows.extend(imported)
            self._handle_save_sheet()
            self.banner.show_message(
                f"Successfully imported and saved {len(imported)} new validation test(s)!",
                level=NotificationLevel.SUCCESS,
                title="Import Successful",
            )
        except Exception as exc:
            logger.exception("Failed to import sheet: %s", exc)
            self.banner.show_message(
                f"Import failed: {format_safe_user_error(exc)}",
                level=NotificationLevel.ERROR,
                title="Import Error",
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
            config={},
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
            blob = f"{r.workspace_name} {r.report_name} {r.validation_type_display} {r.table_name} {r.column_name} {r.measure_name} {r.conditions_summary}".lower()
            self.sheet_table.setRowHidden(row_idx, q not in blob)

    def _update_stats_label(self) -> None:
        total = len(self._rows)
        enabled = sum(1 for r in self._rows if r.enabled)
        unique_ws = len(set(r.workspace_id for r in self._rows if r.workspace_id))
        self.lbl_row_stats.setText(
            f"Total Rows: {total}  |  Enabled: {enabled}  |  Workspaces: {unique_ws}"
        )
