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


def test_animated_combo_wheel_event_ignored_when_popup_closed(qtbot) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent

    combo = AnimatedComboBox()
    qtbot.addWidget(combo)
    combo.show()
    combo.addItems(["First", "Second", "Third"])
    assert combo.currentIndex() == 0

    # Simulate wheel event while popup is closed
    wheel_ev = QWheelEvent(
        QPoint(10, 10),
        QPoint(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    combo.wheelEvent(wheel_ev)

    # Event was ignored so it passes to parent table, and index is unchanged
    assert not wheel_ev.isAccepted()
    assert combo.currentIndex() == 0


def test_smooth_scrolling_on_table(qtbot) -> None:
    from PySide6.QtWidgets import QAbstractItemView, QTableWidget
    from app.ui.widgets.smooth_scroller import apply_smooth_scrolling

    table = QTableWidget(50, 5)
    qtbot.addWidget(table)
    apply_smooth_scrolling(table)

    assert table.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
    assert table.horizontalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
    assert table.verticalScrollBar().singleStep() == 20

