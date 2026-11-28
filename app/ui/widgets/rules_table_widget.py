"""Reusable table widget managing validation rule configuration (BRD 5.2)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.integrations.powerbi.models import DatasetMetadata
from app.services.rule_service import (
    TARGET_TYPE_COLUMN,
    TARGET_TYPE_MEASURE,
    TARGET_TYPE_MODEL,
    RuleInput,
    RuleRecord,
    RuleService,
)
from app.ui.dialogs.advanced_settings_dialog import AdvancedSettingsDialog
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.dialogs.rule_editor_dialog import RuleEditorDialog

if TYPE_CHECKING:
    from app.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)


class ValidationRulesTableWidget(QFrame):
    """Row-based validation rule configuration table with full CRUD, reorder, and advanced settings."""

    rules_changed = Signal(int)  # workspace_registration_id

    def __init__(
        self,
        *,
        rule_service: RuleService,
        metadata_service: MetadataService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rule_service = rule_service
        self._metadata_service = metadata_service
        self._registration_id: int | None = None
        self._registration_display_name: str = ""
        self._cached_metadata: DatasetMetadata | None = None
        self._rules: list[RuleRecord] = []

        self.setObjectName("RulesTableWidget")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Action Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.add_button = QPushButton("+ Add Rule")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; font-weight: 600; padding: 7px 14px; border-radius: 6px;"
        )
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self._handle_add_rule)
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Edit Rule")
        self.edit_button.setObjectName("SecondaryButton")
        self.edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_button.clicked.connect(self._handle_edit_rule)
        toolbar.addWidget(self.edit_button)

        self.duplicate_button = QPushButton("Duplicate Rule")
        self.duplicate_button.setObjectName("SecondaryButton")
        self.duplicate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.duplicate_button.clicked.connect(self._handle_duplicate_rule)
        toolbar.addWidget(self.duplicate_button)

        self.toggle_button = QPushButton("Toggle Enabled")
        self.toggle_button.setObjectName("SecondaryButton")
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.clicked.connect(self._handle_toggle_enabled)
        toolbar.addWidget(self.toggle_button)

        self.move_up_button = QPushButton("▲ Move Up")
        self.move_up_button.setObjectName("SecondaryButton")
        self.move_up_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.move_up_button.clicked.connect(lambda: self._handle_move(-1))
        toolbar.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("▼ Move Down")
        self.move_down_button.setObjectName("SecondaryButton")
        self.move_down_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.move_down_button.clicked.connect(lambda: self._handle_move(1))
        toolbar.addWidget(self.move_down_button)

        self.delete_button = QPushButton("Delete Rule")
        self.delete_button.setObjectName("DangerButton")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self._handle_delete_rule)
        toolbar.addWidget(self.delete_button)

        toolbar.addStretch(1)

        self.count_badge = QLabel("0 rules configured")
        self.count_badge.setStyleSheet("color: #475569; font-size: 12px; font-weight: 500;")
        toolbar.addWidget(self.count_badge)

        layout.addLayout(toolbar)

        # Rules Table
        self.table = QTableWidget()
        self.table.setObjectName("DataTable")
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "SR",
            "Enabled",
            "Rule Name",
            "Target Type",
            "Table",
            "Column / Measure",
            "Validation Check",
            "Conditions / Summary",
            "Advanced",
        ])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda _item: self._handle_edit_rule())
        self.table.itemSelectionChanged.connect(self._update_toolbar_state)

        layout.addWidget(self.table)
        self._update_toolbar_state()

    def set_registration(
        self,
        registration_id: int | None,
        display_name: str = "",
        metadata: DatasetMetadata | None = None,
    ) -> None:
        """Set the active workspace registration context and load rules from SQLite."""
        self._registration_id = registration_id
        self._registration_display_name = display_name
        self._cached_metadata = metadata
        self.refresh_rules()

    def refresh_rules(self) -> None:
        """Reload rules from SQLite for the active registration."""
        if self._registration_id is None:
            self._rules = []
            self._populate_table()
            return

        try:
            self._rules = self._rule_service.list_rules(self._registration_id)
        except Exception as exc:
            logger.warning("Failed loading rules for registration %s: %s", self._registration_id, exc)
            self._rules = []

        self._populate_table()

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._rules))

        for row_idx, rule in enumerate(self._rules):
            # 0. SR
            sr_item = QTableWidgetItem(str(row_idx + 1))
            sr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 0, sr_item)

            # 1. Enabled
            enabled_str = "✓ Yes" if rule.enabled else "✗ No"
            en_item = QTableWidgetItem(enabled_str)
            en_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if rule.enabled:
                en_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                en_item.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row_idx, 1, en_item)

            # 2. Rule Name
            name_item = QTableWidgetItem(rule.rule_name)
            name_item.setData(Qt.ItemDataRole.UserRole, rule.id)
            self.table.setItem(row_idx, 2, name_item)

            # 3. Target Type
            type_item = QTableWidgetItem(rule.target_type_display)
            self.table.setItem(row_idx, 3, type_item)

            # 4. Table
            tbl_item = QTableWidgetItem(rule.table_name or "-")
            self.table.setItem(row_idx, 4, tbl_item)

            # 5. Column / Measure
            col_meas = rule.measure_name if rule.target_type == TARGET_TYPE_MEASURE else (rule.column_name or "-")
            cm_item = QTableWidgetItem(col_meas or "-")
            self.table.setItem(row_idx, 5, cm_item)

            # 6. Validation Check
            check_item = QTableWidgetItem(rule.validation_type_display)
            self.table.setItem(row_idx, 6, check_item)

            # 7. Conditions / Summary
            summary_item = QTableWidgetItem(rule.conditions_summary)
            self.table.setItem(row_idx, 7, summary_item)

            # 8. Advanced Button
            adv_btn = QPushButton("⚙ Config")
            adv_btn.setObjectName("SecondaryButton")
            adv_btn.setStyleSheet(
                "background-color: #FFFFFF; color: #2563EB; border: 1px solid #CBD5E1; "
                "font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 4px;"
            )
            adv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            adv_btn.clicked.connect(lambda _checked=False, r=rule: self._open_advanced_for_rule(r))
            self.table.setCellWidget(row_idx, 8, adv_btn)

        n_enabled = sum(1 for r in self._rules if r.enabled)
        self.count_badge.setText(f"{len(self._rules)} rule(s) ({n_enabled} enabled)")
        self._update_toolbar_state()

    def _update_toolbar_state(self) -> None:
        has_context = self._registration_id is not None
        has_selection = self.selected_rule is not None
        self.add_button.setEnabled(has_context)
        self.edit_button.setEnabled(has_selection)
        self.duplicate_button.setEnabled(has_selection)
        self.toggle_button.setEnabled(has_selection)
        self.move_up_button.setEnabled(has_selection)
        self.move_down_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    @property
    def selected_rule(self) -> RuleRecord | None:
        row = self.table.currentRow()
        if row < 0:
            selected_items = self.table.selectedItems()
            if selected_items:
                row = selected_items[0].row()
        if 0 <= row < len(self._rules):
            return self._rules[row]
        return None

    def _handle_add_rule(self) -> None:
        if self._registration_id is None:
            return

        dlg = RuleEditorDialog(
            workspace_registration_id=self._registration_id,
            registration_display_name=self._registration_display_name,
            metadata=self._cached_metadata,
            parent=self,
        )
        if dlg.exec() == RuleEditorDialog.DialogCode.Accepted and dlg.rule_input is not None:
            self._rule_service.create_rule(dlg.rule_input)
            self.refresh_rules()
            self.rules_changed.emit(self._registration_id)

    def _handle_edit_rule(self) -> None:
        rule = self.selected_rule
        if rule is None or self._registration_id is None:
            return

        dlg = RuleEditorDialog(
            workspace_registration_id=self._registration_id,
            registration_display_name=self._registration_display_name,
            existing_rule=rule,
            metadata=self._cached_metadata,
            parent=self,
        )
        if dlg.exec() == RuleEditorDialog.DialogCode.Accepted and dlg.rule_input is not None:
            self._rule_service.update_rule(rule.id, dlg.rule_input)
            self.refresh_rules()
            self.rules_changed.emit(self._registration_id)

    def _handle_duplicate_rule(self) -> None:
        rule = self.selected_rule
        if rule is None or self._registration_id is None:
            return

        self._rule_service.duplicate_rule(rule.id)
        self.refresh_rules()
        self.rules_changed.emit(self._registration_id)

    def _handle_toggle_enabled(self) -> None:
        rule = self.selected_rule
        if rule is None or self._registration_id is None:
            return

        self._rule_service.toggle_enabled(rule.id)
        self.refresh_rules()
        self.rules_changed.emit(self._registration_id)

    def _handle_move(self, delta: int) -> None:
        current_idx = self.table.currentRow()
        if current_idx < 0:
            selected_items = self.table.selectedItems()
            if selected_items:
                current_idx = selected_items[0].row()
        if current_idx < 0 or self._registration_id is None:
            return

        target_idx = current_idx + delta
        if 0 <= target_idx < len(self._rules):
            # Swap positions
            rule_ids = [r.id for r in self._rules]
            rule_ids[current_idx], rule_ids[target_idx] = rule_ids[target_idx], rule_ids[current_idx]
            self._rule_service.reorder_rules(self._registration_id, rule_ids)
            self.refresh_rules()
            self.table.selectRow(target_idx)
            self.rules_changed.emit(self._registration_id)

    def _handle_delete_rule(self) -> None:
        rule = self.selected_rule
        if rule is None or self._registration_id is None:
            return

        confirmed = ConfirmDialog.ask(
            self,
            title="Delete Validation Rule",
            message=f"Are you sure you want to delete '{rule.rule_name}'?",
            detail="This validation rule will be permanently deleted from configuration.",
            confirm_text="Delete",
            cancel_text="Cancel",
            destructive=True,
        )
        if confirmed:
            self._rule_service.delete_rule(rule.id)
            self.refresh_rules()
            self.rules_changed.emit(self._registration_id)

    def _open_advanced_for_rule(self, rule: RuleRecord) -> None:
        if self._registration_id is None:
            return

        dlg = AdvancedSettingsDialog(
            rule_name=rule.rule_name,
            validation_type=rule.validation_type,
            current_config=rule.config,
            parent=self,
        )
        if dlg.exec() == AdvancedSettingsDialog.DialogCode.Accepted:
            # Update the rule's config in SQLite
            updated_input = RuleInput(
                workspace_registration_id=rule.workspace_registration_id,
                rule_name=rule.rule_name,
                target_type=rule.target_type,
                validation_type=rule.validation_type,
                enabled=rule.enabled,
                table_name=rule.table_name,
                column_name=rule.column_name,
                measure_name=rule.measure_name,
                config=dlg.config,
                display_order=rule.display_order,
            )
            self._rule_service.update_rule(rule.id, updated_input)
            self.refresh_rules()
            self.rules_changed.emit(self._registration_id)
