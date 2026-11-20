"""Settings page managing workspace/dataset registrations (Stage 5) and upcoming rule editor."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.exceptions import PersistenceError, ValidationConfigError, format_safe_user_error
from app.core.status import NotificationLevel, RefreshStatus
from app.integrations.file_import import RegistrationInput
from app.integrations.powerbi.models import AccessVerificationResult, DatasetMetadata, PowerBIWorkspace
from app.services.registry_service import RegistrationRecord, RegistryService
from app.ui.dialogs.confirm_dialog import ConfirmDialog
from app.ui.dialogs.dax_inspector_dialog import DaxInspectorDialog
from app.ui.dialogs.import_registrations_dialog import ImportRegistrationsDialog
from app.ui.dialogs.quick_add_workspaces_dialog import QuickAddWorkspacesDialog
from app.ui.dialogs.refresh_details_dialog import RefreshDetailsDialog
from app.ui.dialogs.registration_dialog import RegistrationDialog
from app.ui.models.dict_table_model import ColumnSpec
from app.ui.widgets.data_table import DataTableWidget
from app.ui.widgets.metadata_selector_widget import MetadataSelectorWidget
from app.ui.widgets.notification_banner import NotificationBanner
from app.ui.widgets.rules_table_widget import ValidationRulesTableWidget
from app.ui.widgets.searchable_combo import SearchableComboBox

if TYPE_CHECKING:
    from app.services.dax_service import DaxQueryService
    from app.services.metadata_service import MetadataService
    from app.services.powerbi_service import PowerBIService
    from app.services.refresh_service import RefreshService
    from app.services.rule_service import RuleService

_REGISTRY_COLUMNS: list[ColumnSpec] = [
    ColumnSpec(key="active", header="Active", alignment=Qt.AlignmentFlag.AlignCenter),
    ColumnSpec(key="workspace_name", header="Workspace Name"),
    ColumnSpec(key="workspace_id", header="Workspace ID"),
    ColumnSpec(key="report_name", header="Report Name"),
    ColumnSpec(key="dataset_name", header="Dataset Name"),
    ColumnSpec(key="dataset_id", header="Dataset ID"),
    ColumnSpec(key="access_status", header="Access Status"),
    ColumnSpec(key="refresh_status", header="Latest Refresh"),
]


class SettingsPage(QWidget):
    """Validation Settings page with Workspace & Dataset Registry (Stage 5)."""

    verify_registration_requested = Signal(int, str, str, str)
    registrations_changed = Signal()

    def __init__(
        self,
        *,
        registry_service: RegistryService | None = None,
        metadata_service: MetadataService | None = None,
        powerbi_service: PowerBIService | None = None,
        rule_service: RuleService | None = None,
        refresh_service: RefreshService | None = None,
        dax_service: DaxQueryService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry_service
        self._metadata_service = metadata_service
        self._powerbi_service = powerbi_service
        self._refresh_service = refresh_service
        self._dax_service = dax_service
        if rule_service is None and registry_service is not None and getattr(registry_service, "_db", None) is not None:
            from app.services.rule_service import RuleService as _RuleSvc
            rule_service = _RuleSvc(registry_service._db)
        self._rule_service = rule_service
        self._records: dict[int, RegistrationRecord] = {}
        self._access_status_by_id: dict[int, str] = {}
        self._build_ui()
        self._connect_metadata_service()
        self.refresh_registrations()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("PageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget(scroll_area)
        container.setObjectName("PageContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # Page Header (matching mockup right screen)
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel("Validation Settings")
        title.setObjectName("PageTitle")
        title_col.addWidget(title)

        subtitle = QLabel("Configure workspace registrations, semantic models, and validation rules.")
        subtitle.setObjectName("PageSubtitle")
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col, stretch=1)

        badge = QLabel("Stage 9: DAX Query Execution Active")
        badge.setObjectName("StageBadge")
        header_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        # Section 1: Workspace & Dataset Configuration
        registry_card = QFrame()
        registry_card.setObjectName("Card")
        reg_layout = QVBoxLayout(registry_card)
        reg_layout.setContentsMargins(22, 20, 22, 20)
        reg_layout.setSpacing(12)

        sec1_header = QHBoxLayout()
        sec1_title = QLabel("1. Workspace & Dataset Configuration")
        sec1_title.setObjectName("SectionTitle")
        sec1_header.addWidget(sec1_title, stretch=1)

        self.export_template_button = QPushButton("Export Template")
        self.export_template_button.setObjectName("SecondaryButton")
        self.export_template_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_template_button.clicked.connect(self._handle_export_template)
        sec1_header.addWidget(self.export_template_button)

        self.import_button = QPushButton("Import CSV / Excel")
        self.import_button.setObjectName("SecondaryButton")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._handle_import_clicked)
        sec1_header.addWidget(self.import_button)

        self.add_button = QPushButton("+ Add Custom")
        self.add_button.setObjectName("SecondaryButton")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self._handle_add_clicked)
        sec1_header.addWidget(self.add_button)

        self.quick_add_button = QPushButton("✨ Quick Add from Power BI")
        self.quick_add_button.setObjectName("PrimaryButton")
        self.quick_add_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; padding: 7px 16px; border-radius: 6px;"
        )
        self.quick_add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quick_add_button.clicked.connect(self._handle_quick_add_clicked)
        sec1_header.addWidget(self.quick_add_button)

        reg_layout.addLayout(sec1_header)

        self.registry_banner = NotificationBanner(registry_card)
        reg_layout.addWidget(self.registry_banner)

        self.registry_table = DataTableWidget(
            columns=_REGISTRY_COLUMNS,
            rows=[],
            show_search=True,
            filter_column_key="active",
            filter_options=["Active", "Inactive"],
            parent=registry_card,
        )
        self.registry_table.setMinimumHeight(230)
        self.registry_table.table_view.setColumnWidth(0, 72)
        self.registry_table.table_view.setColumnWidth(1, 150)
        self.registry_table.table_view.setColumnWidth(2, 185)
        self.registry_table.table_view.setColumnWidth(3, 150)
        self.registry_table.table_view.setColumnWidth(4, 140)
        self.registry_table.table_view.setColumnWidth(5, 185)
        self.registry_table.row_activated.connect(lambda _row: self._handle_edit_clicked())
        reg_layout.addWidget(self.registry_table)

        # Row Action Bar
        row_actions = QHBoxLayout()
        row_actions.setSpacing(8)

        self.edit_button = QPushButton("Edit Selected")
        self.edit_button.setObjectName("SecondaryButton")
        self.edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_button.clicked.connect(self._handle_edit_clicked)
        row_actions.addWidget(self.edit_button)

        self.toggle_active_button = QPushButton("Toggle Active")
        self.toggle_active_button.setObjectName("SecondaryButton")
        self.toggle_active_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_active_button.clicked.connect(self._handle_toggle_active)
        row_actions.addWidget(self.toggle_active_button)

        self.verify_access_button = QPushButton("Verify Access")
        self.verify_access_button.setObjectName("SecondaryButton")
        self.verify_access_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.verify_access_button.clicked.connect(self._handle_verify_access)
        row_actions.addWidget(self.verify_access_button)

        self.refresh_history_button = QPushButton("Refresh History...")
        self.refresh_history_button.setObjectName("SecondaryButton")
        self.refresh_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_history_button.clicked.connect(self._handle_refresh_history_clicked)
        row_actions.addWidget(self.refresh_history_button)

        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.setObjectName("DangerButton")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self._handle_delete_clicked)
        row_actions.addWidget(self.delete_button)

        row_actions.addStretch(1)

        self.count_label = QLabel("0 registrations")
        self.count_label.setObjectName("PageSubtitle")
        row_actions.addWidget(self.count_label)

        reg_layout.addLayout(row_actions)
        layout.addWidget(registry_card)

        # Section 2: Semantic Model Metadata Discovery (Stage 6)
        metadata_card = QFrame()
        metadata_card.setObjectName("Card")
        meta_layout = QVBoxLayout(metadata_card)
        meta_layout.setContentsMargins(22, 20, 22, 20)
        meta_layout.setSpacing(12)

        meta_header = QHBoxLayout()
        sec2_title = QLabel("2. Semantic Model Metadata Discovery")
        sec2_title.setObjectName("SectionTitle")
        meta_header.addWidget(sec2_title, stretch=1)

        self.inspect_dax_button = QPushButton("▶ Inspect Measure DAX...")
        self.inspect_dax_button.setObjectName("SecondaryButton")
        self.inspect_dax_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.inspect_dax_button.clicked.connect(self._handle_inspect_dax_clicked)
        meta_header.addWidget(self.inspect_dax_button)

        meta_layout.addLayout(meta_header)

        # Target dataset selector row
        target_select_row = QHBoxLayout()
        target_select_row.setSpacing(10)
        target_label = QLabel("Select Target Model:")
        target_label.setStyleSheet("color: #0F172A; font-weight: 600; font-size: 13px;")
        target_select_row.addWidget(target_label)

        self.dataset_selector_combo = SearchableComboBox()
        self.dataset_selector_combo.currentIndexChanged.connect(self._handle_dataset_selection_changed)
        target_select_row.addWidget(self.dataset_selector_combo, stretch=1)
        meta_layout.addLayout(target_select_row)

        self.metadata_selector = MetadataSelectorWidget()
        self.metadata_selector.discovery_requested.connect(self._handle_discovery_requested)
        meta_layout.addWidget(self.metadata_selector)

        layout.addWidget(metadata_card)

        # Section 3: Validation Checks Configuration (Stage 7)
        rules_card = QFrame()
        rules_card.setObjectName("Card")
        rules_layout = QVBoxLayout(rules_card)
        rules_layout.setContentsMargins(22, 20, 22, 20)
        rules_layout.setSpacing(12)

        sec3_header = QHBoxLayout()
        sec3_title = QLabel("3. Validation Rules Configuration")
        sec3_title.setObjectName("SectionTitle")
        sec3_header.addWidget(sec3_title, stretch=1)
        rules_layout.addLayout(sec3_header)

        sec3_note = QLabel(
            "Configure row-based validation rules (Null, Duplicate, Latest Date, Row Count, "
            "DAX Measure, Anomaly, Refresh) for the selected semantic model. Click '⚙ Config' to edit row-level thresholds."
        )
        sec3_note.setObjectName("InfoBanner")
        sec3_note.setWordWrap(True)
        rules_layout.addWidget(sec3_note)

        self.rules_table = ValidationRulesTableWidget(
            rule_service=self._rule_service,
            metadata_service=self._metadata_service,
            parent=rules_card,
        )
        rules_layout.addWidget(self.rules_table)

        layout.addWidget(rules_card)
        layout.addStretch(1)

        scroll_area.setWidget(container)
        outer.addWidget(scroll_area)

    def refresh_registrations(self) -> None:
        """Reload all saved registrations from SQLite into the table."""
        if self._registry is None:
            self._records = {}
            self.registry_table.set_rows([])
            self.count_label.setText("0 registrations")
            return

        records = self._registry.list_registrations()
        self._records = {r.id: r for r in records}
        table_rows = []
        for r in records:
            ref_status = "No History"
            if self._refresh_service is not None:
                latest_ref = self._refresh_service.get_latest_attempt(r.id)
                if latest_ref is not None:
                    status_str = latest_ref.status.value
                    if latest_ref.status == RefreshStatus.IN_PROGRESS:
                        ref_status = "In Progress"
                    elif latest_ref.age_hours is not None:
                        ref_status = f"{status_str} ({latest_ref.age_hours}h ago)"
                    else:
                        ref_status = status_str

            table_rows.append({
                "id": r.id,
                "active": "Active" if r.is_active else "Inactive",
                "workspace_name": r.workspace_name,
                "workspace_id": r.workspace_id,
                "report_name": r.report_name,
                "dataset_name": r.dataset_name or "",
                "dataset_id": r.dataset_id,
                "access_status": self._access_status_by_id.get(r.id, "Not verified"),
                "refresh_status": ref_status,
            })
        self.registry_table.set_rows(table_rows)

        active_count = sum(1 for r in records if r.is_active)
        self.count_label.setText(
            f"{len(records)} registration(s) ({active_count} active)"
        )

        # Update dataset selector combo for metadata discovery
        self.dataset_selector_combo.blockSignals(True)
        self.dataset_selector_combo.clear()
        if not records:
            self.dataset_selector_combo.addItem("-- No registered datasets --", None)
            self.metadata_selector.set_active_dataset("", "")
            if hasattr(self, "rules_table"):
                self.rules_table.set_registration(None, "")
        else:
            self.dataset_selector_combo.addItem("-- Select registered model --", None)
            for r in records:
                label = f"{r.dataset_name or r.report_name}  •  {r.workspace_name} ({r.dataset_id[:8]}...)"
                self.dataset_selector_combo.addItem(
                    label,
                    (r.workspace_id, r.dataset_id, r.id, f"{r.dataset_name or r.report_name}"),
                )
            active_idx = next((i + 1 for i, r in enumerate(records) if r.is_active), 1 if records else 0)
            self.dataset_selector_combo.setCurrentIndex(active_idx)
            self._apply_dataset_selection(self.dataset_selector_combo.itemData(active_idx))
        self.dataset_selector_combo.blockSignals(False)

    def _connect_metadata_service(self) -> None:
        if self._metadata_service is not None:
            self._metadata_service.metadata_loaded.connect(self._on_metadata_loaded)
            self._metadata_service.metadata_failed.connect(self._on_metadata_failed)
            self._metadata_service.busy_changed.connect(self.metadata_selector.set_busy)

    def _on_metadata_loaded(self, metadata: DatasetMetadata) -> None:
        if (
            self.metadata_selector._dataset_id
            and self.metadata_selector._dataset_id.lower() == metadata.dataset_id.lower()
        ):
            self.metadata_selector.apply_metadata(metadata)
            if hasattr(self, "rules_table"):
                self.rules_table._cached_metadata = metadata

    def _on_metadata_failed(self, dataset_id: str, error_message: str) -> None:
        if (
            self.metadata_selector._dataset_id
            and self.metadata_selector._dataset_id.lower() == dataset_id.lower()
        ):
            self.metadata_selector.apply_metadata(
                DatasetMetadata(
                    dataset_id=dataset_id,
                    workspace_id=self.metadata_selector._workspace_id,
                    is_supported=False,
                    error_message=error_message,
                )
            )

    def _handle_dataset_selection_changed(self, index: int) -> None:
        data = self.dataset_selector_combo.itemData(index)
        self._apply_dataset_selection(data)

    def _apply_dataset_selection(self, data: Any) -> None:
        if isinstance(data, tuple) and len(data) >= 2:
            ws_id = data[0]
            ds_id = data[1]
            reg_id = data[2] if len(data) > 2 else None
            disp_name = data[3] if len(data) > 3 else f"{ds_id[:8]}..."

            self.metadata_selector.set_active_dataset(ws_id, ds_id)
            cached = None
            if self._metadata_service is not None:
                cached = self._metadata_service.get_cached_metadata(ws_id, ds_id)
                if cached is not None:
                    self.metadata_selector.apply_metadata(cached)

            if hasattr(self, "rules_table"):
                self.rules_table.set_registration(reg_id, disp_name, cached)
        elif not data and hasattr(self, "rules_table"):
            self.rules_table.set_registration(None, "")

    def _handle_discovery_requested(self, workspace_id: str, dataset_id: str) -> None:
        if self._metadata_service is not None:
            self._metadata_service.fetch_metadata_async(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                force_refresh=True,
            )
        else:
            self.metadata_selector.apply_metadata(
                DatasetMetadata(
                    dataset_id=dataset_id,
                    workspace_id=workspace_id,
                    is_supported=False,
                    error_message="Metadata service is not connected.",
                )
            )

    def _handle_inspect_dax_clicked(self) -> None:
        if self._dax_service is None:
            self.registry_banner.show_message(
                "DAX query execution service is not configured.",
                level=NotificationLevel.ERROR,
                title="Service Unavailable",
            )
            return

        current_data = self.dataset_selector_combo.currentData()
        if not current_data or not isinstance(current_data, tuple):
            self.registry_banner.show_message(
                "Please select a registered semantic model in the dropdown above first.",
                level=NotificationLevel.WARNING,
                title="No Model Selected",
            )
            return

        ws_id, ds_id = current_data[0], current_data[1]
        disp_name = current_data[3] if len(current_data) > 3 else f"{ds_id[:8]}..."
        cached_meta = self._metadata_service.get_cached_metadata(ws_id, ds_id) if self._metadata_service else None
        preselected_measure = self.metadata_selector.selected_measure() or None

        dialog = DaxInspectorDialog(
            workspace_id=ws_id,
            dataset_id=ds_id,
            display_name=disp_name,
            dax_service=self._dax_service,
            metadata=cached_meta,
            preselected_measure=preselected_measure,
            parent=self,
        )
        dialog.exec()

    def selected_registration(self) -> RegistrationRecord | None:
        """Return the currently selected registration record, or None."""
        selection = self.registry_table.table_view.selectionModel()
        if selection is None:
            return None
        indexes = selection.selectedRows()
        if not indexes:
            return None
        source_index = self.registry_table.proxy_model.mapToSource(indexes[0])
        if not source_index.isValid():
            return None
        row_data = self.registry_table.source_model.row_at(source_index.row())
        reg_id = row_data.get("id")
        return self._records.get(int(reg_id)) if reg_id is not None else None

    def set_verification_result(
        self,
        registration_id: int,
        result: AccessVerificationResult,
    ) -> None:
        """Update the table's Access Status column and inline banner after Verify Access."""
        if result.is_verified:
            label = f"Verified ({result.effective_access_level})"
            level = NotificationLevel.WARNING if result.issues else NotificationLevel.SUCCESS
            title = "Verified with Warnings" if result.issues else "Access Verified"
        else:
            label = "Access Failed"
            level = NotificationLevel.ERROR
            title = "Verification Failed"

        self._access_status_by_id[registration_id] = label
        self.refresh_registrations()
        self.registry_banner.show_message(result.summary, level=level, title=title)

    def _handle_quick_add_clicked(self) -> None:
        if self._powerbi_service is None:
            self.registry_banner.show_message(
                "Power BI Service connection is required for quick registration.",
                level=NotificationLevel.WARNING,
                title="Power BI Connection",
            )
            return

        dialog = QuickAddWorkspacesDialog(
            powerbi_service=self._powerbi_service,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_registrations:
            created_count = 0
            errors: list[str] = []
            for item in dialog.selected_registrations:
                try:
                    if self._registry is not None:
                        self._registry.create_registration(item)
                        created_count += 1
                except Exception as exc:
                    errors.append(f"{item.dataset_name or item.report_name}: {format_safe_user_error(exc)}")

            self.refresh_registrations()
            self.registrations_changed.emit()

            if created_count > 0 and not errors:
                self.registry_banner.show_message(
                    f"Successfully registered {created_count} semantic model(s) from Power BI!",
                    level=NotificationLevel.SUCCESS,
                    title="Quick Registration",
                )
            elif created_count > 0 and errors:
                self.registry_banner.show_message(
                    f"Registered {created_count} model(s); {len(errors)} skipped: {errors[0]}",
                    level=NotificationLevel.WARNING,
                    title="Partial Registration",
                )
            elif errors:
                self.registry_banner.show_message(
                    f"Could not register models: {errors[0]}",
                    level=NotificationLevel.ERROR,
                    title="Registration Error",
                )

    def _on_save_another_registration(self, reg_input: RegistrationInput) -> bool:
        if self._registry is None:
            return False
        try:
            self._registry.create_registration(reg_input)
            self.refresh_registrations()
            self.registrations_changed.emit()
            return True
        except Exception as exc:
            self.registry_banner.show_message(
                format_safe_user_error(exc),
                level=NotificationLevel.ERROR,
                title="Could Not Save",
            )
            return False

    def _handle_add_clicked(self) -> None:
        if self._registry is None:
            return
        dialog = RegistrationDialog(
            powerbi_service=self._powerbi_service,
            on_save_another=self._on_save_another_registration,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.registration_input is not None:
            try:
                created = self._registry.create_registration(dialog.registration_input)
            except (PersistenceError, ValidationConfigError) as exc:
                self.registry_banner.show_message(
                    exc.user_message,
                    level=NotificationLevel.ERROR,
                    title="Could Not Save",
                )
                return

            self.refresh_registrations()
            self.registrations_changed.emit()
            self.registry_banner.show_message(
                f"Added '{created.workspace_name} / {created.report_name}'.",
                level=NotificationLevel.SUCCESS,
                title="Saved",
            )

    def _handle_edit_clicked(self) -> None:
        if self._registry is None:
            return
        record = self.selected_registration()
        if record is None:
            self.registry_banner.show_message(
                "Select a registration row to edit.",
                level=NotificationLevel.INFO,
                title="Selection Required",
            )
            return

        dialog = RegistrationDialog(
            existing=record,
            powerbi_service=self._powerbi_service,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.registration_input is not None:
            try:
                updated = self._registry.update_registration(record.id, dialog.registration_input)
            except (PersistenceError, ValidationConfigError) as exc:
                self.registry_banner.show_message(
                    exc.user_message,
                    level=NotificationLevel.ERROR,
                    title="Update Failed",
                )
                return

            self._access_status_by_id.pop(record.id, None)
            self.refresh_registrations()
            self.registrations_changed.emit()
            self.registry_banner.show_message(
                f"Updated '{updated.workspace_name} / {updated.report_name}'.",
                level=NotificationLevel.SUCCESS,
                title="Updated",
            )

    def _handle_toggle_active(self) -> None:
        if self._registry is None:
            return
        record = self.selected_registration()
        if record is None:
            self.registry_banner.show_message(
                "Select a registration row to toggle Active/Inactive.",
                level=NotificationLevel.INFO,
                title="Selection Required",
            )
            return

        updated = self._registry.set_active(record.id, not record.is_active)
        self.refresh_registrations()
        self.registrations_changed.emit()
        state_word = "Active" if updated.is_active else "Inactive"
        self.registry_banner.show_message(
            f"Marked '{updated.report_name}' as {state_word}.",
            level=NotificationLevel.INFO,
            title="Status Updated",
        )

    def _handle_verify_access(self) -> None:
        record = self.selected_registration()
        if record is None:
            self.registry_banner.show_message(
                "Select a registration row to verify Power BI access.",
                level=NotificationLevel.INFO,
                title="Selection Required",
            )
            return

        self.registry_banner.show_message(
            f"Verifying access to '{record.workspace_name} / {record.report_name}'...",
            level=NotificationLevel.INFO,
            title="Verifying",
        )
        self.verify_registration_requested.emit(
            record.id,
            record.workspace_id,
            record.dataset_id,
            record.report_id or "",
        )

    def _handle_refresh_history_clicked(self) -> None:
        record = self.selected_registration()
        if record is None:
            self.registry_banner.show_message(
                "Select a registration row to view its Power BI refresh history.",
                level=NotificationLevel.INFO,
                title="Selection Required",
            )
            return

        if self._refresh_service is None:
            self.registry_banner.show_message(
                "Refresh monitoring service is not initialized.",
                level=NotificationLevel.ERROR,
                title="Service Unavailable",
            )
            return

        ds_name = record.dataset_name or record.report_name
        dialog = RefreshDetailsDialog(
            workspace_registration_id=record.id,
            workspace_id=record.workspace_id,
            dataset_id=record.dataset_id,
            registration_display_name=f"{ds_name} ({record.workspace_name})",
            refresh_service=self._refresh_service,
            parent=self,
        )
        dialog.exec()
        self.refresh_registrations()

    def _handle_delete_clicked(self) -> None:
        if self._registry is None:
            return
        record = self.selected_registration()
        if record is None:
            self.registry_banner.show_message(
                "Select a registration row to delete.",
                level=NotificationLevel.INFO,
                title="Selection Required",
            )
            return

        confirmed = ConfirmDialog.ask(
            self,
            title="Delete Workspace Registration",
            message=f"Delete '{record.workspace_name} / {record.report_name}'?",
            detail="Any validation rules and history linked to this registration will also be deleted.",
            confirm_text="Delete",
            cancel_text="Cancel",
            destructive=True,
        )
        if not confirmed:
            return

        self._registry.delete_registration(record.id)
        self._access_status_by_id.pop(record.id, None)
        self.refresh_registrations()
        self.registrations_changed.emit()
        self.registry_banner.show_message(
            f"Deleted '{record.workspace_name} / {record.report_name}'.",
            level=NotificationLevel.INFO,
            title="Deleted",
        )

    def _handle_import_clicked(self) -> None:
        if self._registry is None:
            return
        dialog = ImportRegistrationsDialog(self._registry, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.confirmed_rows:
            saved_count, errors = self._registry.commit_import(dialog.confirmed_rows)
            self.refresh_registrations()
            self.registrations_changed.emit()

            if errors:
                self.registry_banner.show_message(
                    f"Imported {saved_count} registration(s) with {len(errors)} error(s): {errors[0]}",
                    level=NotificationLevel.WARNING,
                    title="Import Completed with Warnings",
                )
            else:
                self.registry_banner.show_message(
                    f"Successfully imported {saved_count} registration(s).",
                    level=NotificationLevel.SUCCESS,
                    title="Import Complete",
                )

    def _handle_export_template(self) -> None:
        if self._registry is None:
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Blank Registration Template",
            "powerbi_registrations_template.xlsx",
            "Excel Workbook (*.xlsx);;CSV File (*.csv)",
        )
        if not selected:
            return
        try:
            saved_path = self._registry.export_template(Path(selected))
            self.registry_banner.show_message(
                f"Exported blank template to {saved_path}",
                level=NotificationLevel.SUCCESS,
                title="Template Exported",
            )
        except ValidationConfigError as exc:
            self.registry_banner.show_message(
                exc.user_message,
                level=NotificationLevel.ERROR,
                title="Export Failed",
            )
