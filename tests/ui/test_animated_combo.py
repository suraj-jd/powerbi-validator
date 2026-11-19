"""UI and behavior tests for AnimatedComboBox."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox

from app.ui.widgets.animated_combo import AnimatedComboBox


def test_animated_combo_subclasses_qcombobox(qtbot) -> None:
    combo = AnimatedComboBox()
    qtbot.addWidget(combo)
    assert isinstance(combo, QComboBox)
    assert combo.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_animated_combo_items_and_tooltip(qtbot) -> None:
    combo = AnimatedComboBox()
    qtbot.addWidget(combo)
    combo.show()

    combo.addItem("Workspace Alpha (Production)", "ws-alpha")
    combo.addItem("Workspace Beta (Staging)", "ws-beta")

    assert combo.count() == 2
    assert combo.currentText() == "Workspace Alpha (Production)"
    assert combo.currentData() == "ws-alpha"

    # Selecting index updates tooltip
    combo.setCurrentIndex(1)
    assert combo.currentText() == "Workspace Beta (Staging)"
    assert combo.currentData() == "ws-beta"
    assert "Workspace Beta" in combo.toolTip()


def test_animated_combo_popup_show_and_hide(qtbot) -> None:
    combo = AnimatedComboBox()
    qtbot.addWidget(combo)
    combo.show()
    combo.addItems(["Option 1", "Option 2", "Option 3"])

    # Trigger showPopup (starts hardware-accelerated fade and slide animation)
    combo.showPopup()
    popup = combo.view().window()
    assert popup is not None
    assert combo._anim_group is not None

    # Trigger hidePopup stops any running animation cleanly
    combo.hidePopup()
    assert combo._anim_group is None or not combo._anim_group.state().value
