"""Metadata discovery and object selector widget for semantic model validation rules.

Enables searching and selecting discovered tables, columns, and DAX measures,
switching dynamically based on target type, validating object names against
the model before rules are executed, and allowing free-form manual entry fallback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.integrations.powerbi.models import DatasetMetadata
from app.ui.widgets.searchable_combo import SearchableComboBox

if TYPE_CHECKING:
    from app.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)


class MetadataSelectorWidget(QFrame):
    """Reusable widget for discovering, browsing, and validating model objects."""

    target_changed = Signal(str, str, str)  # target_type, table_name, column_or_measure
    discovery_requested = Signal(str, str)  # workspace_id, dataset_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_metadata: DatasetMetadata | None = None
        self._workspace_id: str = ""
        self._dataset_id: str = ""
        self.setObjectName("MetadataSelectorWidget")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header row: Title + Discover Button + Status Pill
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel("Semantic Model Object Discovery")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        header_row.addWidget(title)

        header_row.addStretch(1)

        self._status_pill = QLabel("Ready to discover")
        self._status_pill.setStyleSheet(
            "background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; "
            "font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 12px;"
        )
        header_row.addWidget(self._status_pill)

        self._discover_button = QPushButton("🔍 Discover Metadata")
        self._discover_button.setObjectName("DiscoverMetadataButton")
        self._discover_button.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 600; font-size: 12px; "
            "padding: 7px 16px; border-radius: 6px;"
        )
        self._discover_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._discover_button.clicked.connect(self._handle_discover_clicked)
        header_row.addWidget(self._discover_button)

        layout.addLayout(header_row)

        # Description note
        desc = QLabel(
            "Inspect tables, columns, and DAX measures in the selected semantic model. "
            "Manual entry is always supported as fallback if Execute Queries is restricted."
        )
        desc.setStyleSheet("color: #64748B; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Target Type Radios
        type_row = QHBoxLayout()
        type_row.setSpacing(16)
        type_label = QLabel("Validation Target:")
        type_label.setStyleSheet("color: #334155; font-weight: 600; font-size: 12px;")
        type_row.addWidget(type_label)

        self._type_group = QButtonGroup(self)
        self._radio_column = QRadioButton("Table Column")
        self._radio_measure = QRadioButton("DAX Measure")
        self._radio_model = QRadioButton("Model / Refresh Check")
        self._radio_column.setChecked(True)

        for i, rb in enumerate((self._radio_column, self._radio_measure, self._radio_model)):
            rb.setStyleSheet("color: #1E293B; font-size: 13px; font-weight: 500;")
            self._type_group.addButton(rb, i)
            type_row.addWidget(rb)
        type_row.addStretch(1)
        layout.addLayout(type_row)

        self._type_group.idToggled.connect(self._handle_target_type_changed)

        # Fields layout (Table, Column, Measure)
        self._fields_frame = QFrame()
        self._fields_layout = QVBoxLayout(self._fields_frame)
        self._fields_layout.setContentsMargins(0, 4, 0, 4)
        self._fields_layout.setSpacing(8)

        # 1. Table row
        self._table_row = QHBoxLayout()
        self._table_label = QLabel("Table Name:")
        self._table_label.setFixedWidth(120)
        self._table_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")
        self._table_combo = SearchableComboBox()
        self._table_combo.set_items([], placeholder="-- Select or type Table name --")
        self._table_combo.currentTextChanged.connect(self._handle_table_changed)
        self._table_row.addWidget(self._table_label)
        self._table_row.addWidget(self._table_combo, stretch=1)
        self._fields_layout.addLayout(self._table_row)

        # 2. Column row
        self._column_row = QHBoxLayout()
        self._column_label = QLabel("Column Name:")
        self._column_label.setFixedWidth(120)
        self._column_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")
        self._column_combo = SearchableComboBox()
        self._column_combo.set_items([], placeholder="-- Select or type Column name --")
        self._column_combo.currentTextChanged.connect(self._handle_values_changed)
        self._column_row.addWidget(self._column_label)
        self._column_row.addWidget(self._column_combo, stretch=1)
        self._fields_layout.addLayout(self._column_row)

        # 3. Measure row
        self._measure_row = QHBoxLayout()
        self._measure_label = QLabel("Measure Name:")
        self._measure_label.setFixedWidth(120)
        self._measure_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")
        self._measure_combo = SearchableComboBox()
        self._measure_combo.set_items([], placeholder="-- Select or type DAX Measure --")
        self._measure_combo.currentTextChanged.connect(self._handle_values_changed)
        self._measure_row.addWidget(self._measure_label)
        self._measure_row.addWidget(self._measure_combo, stretch=1)
        self._fields_layout.addLayout(self._measure_row)

        # Model check notice (when Model / Refresh is selected)
        self._model_notice = QLabel("Model and Refresh checks apply to the entire semantic model.")
        self._model_notice.setStyleSheet(
            "color: #0369A1; font-size: 12px; font-style: italic; padding: 8px 0;"
        )
        self._model_notice.setVisible(False)
        self._fields_layout.addWidget(self._model_notice)

        layout.addWidget(self._fields_frame)

        # Validation status row
        val_row = QHBoxLayout()
        val_row.setSpacing(10)

        self._validate_button = QPushButton("✓ Validate Target Object")
        self._validate_button.setObjectName("ValidateTargetButton")
        self._validate_button.setStyleSheet(
            "background-color: #FFFFFF; color: #1E293B; font-size: 12px; font-weight: 600; "
            "padding: 6px 14px; border: 1px solid #CBD5E1; border-radius: 6px;"
        )
        self._validate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._validate_button.clicked.connect(self.validate_current_target)
        val_row.addWidget(self._validate_button)

        self._val_badge = QLabel("")
        self._val_badge.setStyleSheet("font-size: 12px; font-weight: 600;")
        val_row.addWidget(self._val_badge, stretch=1)

        layout.addLayout(val_row)

        # Apply initial visibility
        self._update_field_visibilities()

    def set_active_dataset(self, workspace_id: str, dataset_id: str) -> None:
        """Set the active workspace and dataset context."""
        self._workspace_id = workspace_id.strip()
        self._dataset_id = dataset_id.strip()
        self._current_metadata = None
        self._table_combo.set_items([])
        self._column_combo.set_items([])
        self._measure_combo.set_items([])
        self._val_badge.setText("")
        self._status_pill.setText("Ready to discover")
        self._status_pill.setStyleSheet(
            "background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; "
            "font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 12px;"
        )

    def apply_metadata(self, metadata: DatasetMetadata) -> None:
        """Populate dropdown selectors and update discovery status."""
        self._current_metadata = metadata
        self._discover_button.setEnabled(True)
        self._discover_button.setText("🔍 Re-discover")

        if metadata.is_supported and (metadata.tables or metadata.measures):
            n_tables = len(metadata.tables)
            n_cols = sum(len(t.columns) for t in metadata.tables)
            n_meas = len(metadata.measures)
            pill_text = f"✓ Discovered ({n_tables} tables, {n_cols} cols, {n_meas} measures)"
            self._status_pill.setText(pill_text)
            self._status_pill.setStyleSheet(
                "background-color: #DCFCE7; color: #166534; border: 1px solid #86EFAC; "
                "font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 12px;"
            )
            # Populate tables
            self._table_combo.set_items(metadata.table_names)
            # Populate measures
            self._measure_combo.set_items(metadata.measure_names)
        else:
            reason = "Metadata discovery unavailable"
            if metadata.error_message:
                reason = "Execute Queries restricted"
            self._status_pill.setText(f"⚠ {reason} (manual entry enabled)")
            self._status_pill.setStyleSheet(
                "background-color: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; "
                "font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 12px;"
            )

        self._handle_table_changed(self._table_combo.current_text())
        self.validate_current_target()

    def set_busy(self, is_busy: bool) -> None:
        """Update button state during discovery."""
        self._discover_button.setEnabled(not is_busy)
        if is_busy:
            self._discover_button.setText("⏳ Discovering...")
            self._status_pill.setText("Querying model schema...")
            self._status_pill.setStyleSheet(
                "background-color: #E0F2FE; color: #0369A1; border: 1px solid #BAE6FD; "
                "font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 12px;"
            )
        else:
            self._discover_button.setText("🔍 Discover Metadata")

    def _handle_discover_clicked(self) -> None:
        if not self._dataset_id:
            self._val_badge.setText("⚠ Please select or register a dataset first.")
            self._val_badge.setStyleSheet("color: #F87171; font-size: 11px; font-weight: 600;")
            return
        self.discovery_requested.emit(self._workspace_id, self._dataset_id)

    def _handle_target_type_changed(self, *_args: object) -> None:
        self._update_field_visibilities()
        self._emit_target_changed()
        self.validate_current_target()

    def _update_field_visibilities(self) -> None:
        is_col = self._radio_column.isChecked()
        is_meas = self._radio_measure.isChecked()
        is_model = self._radio_model.isChecked()

        # Table is visible for Column check, or optional for Measure check
        self._table_label.setText("Table Name:" if is_col else "Home Table (opt):")
        self._table_label.setVisible(is_col or is_meas)
        self._table_combo.setVisible(is_col or is_meas)

        # Column is only for Column check
        self._column_label.setVisible(is_col)
        self._column_combo.setVisible(is_col)

        # Measure is only for Measure check
        self._measure_label.setVisible(is_meas)
        self._measure_combo.setVisible(is_meas)

        # Notice for Model check
        self._model_notice.setVisible(is_model)
        self._validate_button.setVisible(not is_model)

    def _handle_table_changed(self, table_name: str) -> None:
        """When selected table changes, dynamically filter column combo options."""
        cols: list[str] = []
        if self._current_metadata is not None and table_name:
            tbl = self._current_metadata.get_table(table_name)
            if tbl is not None:
                cols = tbl.column_names
        self._column_combo.set_items(cols, placeholder="-- Select or type Column name --")
        self._emit_target_changed()
        self.validate_current_target()

    def _handle_values_changed(self, *_args: object) -> None:
        self._emit_target_changed()
        self.validate_current_target()

    def _emit_target_changed(self) -> None:
        t_type = self.target_type
        tbl = self.selected_table
        col_or_meas = self.selected_column if t_type == "column" else self.selected_measure
        self.target_changed.emit(t_type, tbl, col_or_meas)

    @property
    def target_type(self) -> str:
        if self._radio_measure.isChecked():
            return "measure"
        if self._radio_model.isChecked():
            return "model"
        return "column"

    @property
    def selected_table(self) -> str:
        return self._table_combo.current_text()

    @property
    def selected_column(self) -> str:
        return self._column_combo.current_text()

    @property
    def selected_measure(self) -> str:
        return self._measure_combo.current_text()

    def set_target(self, target_type: str, table_name: str, column_or_measure: str) -> None:
        """Programmatically configure target fields (e.g. when editing a rule)."""
        normalized = target_type.strip().lower()
        if normalized in ("measure", "dax_measure"):
            self._radio_measure.setChecked(True)
            self._table_combo.set_manual_text(table_name)
            self._measure_combo.set_manual_text(column_or_measure)
        elif normalized in ("model", "refresh"):
            self._radio_model.setChecked(True)
        else:
            self._radio_column.setChecked(True)
            self._table_combo.set_manual_text(table_name)
            self._handle_table_changed(table_name)
            self._column_combo.set_manual_text(column_or_measure)
        self.validate_current_target()

    def validate_current_target(self) -> tuple[bool, str]:
        """Validate target against cached metadata and display visual badge."""
        t_type = self.target_type
        if t_type == "model":
            self._val_badge.setText("✓ Model check applies to entire dataset.")
            self._val_badge.setStyleSheet("color: #0284C7; font-size: 11px;")
            return True, "Model check applies to entire dataset."

        col_or_meas = self.selected_column if t_type == "column" else self.selected_measure
        tbl = self.selected_table

        if self._current_metadata is None:
            self._val_badge.setText("ℹ Unverified (metadata not loaded; manual entry will run).")
            self._val_badge.setStyleSheet("color: #64748B; font-size: 11px;")
            return True, "Unverified"

        is_valid, msg = self._current_metadata.validate_object(t_type, tbl, col_or_meas)
        if is_valid:
            self._val_badge.setText(f"✓ {msg}")
            self._val_badge.setStyleSheet("color: #16A34A; font-size: 11px; font-weight: 600;")
        else:
            self._val_badge.setText(f"✗ {msg}")
            self._val_badge.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600;")
        return is_valid, msg
