"""Stage 0 tests verifying desktop shell startup, navigation, resizing, and clean exit."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from app import APP_NAME, APP_VERSION
from app.ui.main_window import MainWindow


def test_main_window_initial_state(qtbot) -> None:
    """Main window opens with title, version, icon, and Home active by default."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == f"{APP_NAME} v{APP_VERSION}"
    assert not window.windowIcon().isNull()
    assert window.current_page_key == "home"
    assert window._nav_buttons["home"].isChecked()
    assert "Home" in window.statusBar().currentMessage()


@pytest.mark.parametrize("page_key,expected_label", [
    ("settings", "Settings"),
    ("history", "History"),
    ("about", "About"),
    ("home", "Home"),
])
def test_sidebar_navigation_switches_pages(qtbot, page_key: str, expected_label: str) -> None:
    """Clicking each sidebar navigation button switches to the corresponding page."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    button = window._nav_buttons[page_key]
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert window.current_page_key == page_key
    assert button.isChecked()
    assert window._stack.currentWidget() is window._pages[page_key]
    assert expected_label in window.statusBar().currentMessage()


def test_unknown_page_raises_value_error(qtbot) -> None:
    """Navigating to an unregistered page key fails explicitly."""
    window = MainWindow()
    qtbot.addWidget(window)

    with pytest.raises(ValueError, match="Unknown page key"):
        window.navigate_to("nonexistent")


def test_window_resizes_and_respects_minimum_size(qtbot) -> None:
    """Window resizes freely above its minimum size."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    window.resize(1360, 840)
    assert window.width() >= 1360
    assert window.height() >= 840

    assert window.minimumWidth() == 900
    assert window.minimumHeight() == 600


def test_exit_button_closes_window_cleanly(qtbot) -> None:
    """Clicking the sidebar Exit button closes the window cleanly."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.isVisible()
    qtbot.mouseClick(window._exit_button, Qt.MouseButton.LeftButton)
    assert not window.isVisible()
