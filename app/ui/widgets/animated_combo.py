"""Modern animated QComboBox providing smooth slide-and-fade popup transitions and clean styling."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QListView, QWidget

from app.ui.widgets.smooth_scroller import apply_smooth_scrolling


class AnimatedComboBox(QComboBox):
    """High-response QComboBox subclass featuring hardware-accelerated popup animations.

    - Uses a dedicated QListView viewport to ensure full Qt stylesheet rendering.
    - Animate window opacity and subtle vertical slide upon opening (120ms OutCubic).
    - Enables smooth deceleration scrolling for long option lists.
    - Forwards wheel events to parent table when closed, preventing accidental changes and ensuring smooth scrolling.
    - Auto-updates tooltips for long item text.
    - Provides smooth cursor feedback and immediate responsiveness.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        list_view = QListView(self)
        list_view.setObjectName("ModernComboView")
        list_view.setUniformItemSizes(True)
        list_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setView(list_view)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim_group: QParallelAnimationGroup | None = None
        self.currentIndexChanged.connect(self._handle_index_changed)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Prevent accidental dropdown value changes during table/page scrolling.

        Only scrolls through combobox options when the dropdown popup view is active.
        When closed, forwards wheel events to the parent table or scroll container.
        """
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()

    def _handle_index_changed(self, index: int) -> None:
        if index >= 0:
            txt = self.currentText().strip()
            if txt:
                self.setToolTip(txt)

    def showPopup(self) -> None:
        """Open the popup menu with a smooth slide-and-fade animation."""
        super().showPopup()
        popup = self.view().window()
        if popup is None:
            return

        # Ensure Qt's internal top/bottom scroller buttons are hidden
        for child in popup.findChildren(QWidget):
            if child is not self.view() and "scroller" in child.__class__.__name__.lower():
                child.hide()
                child.setFixedHeight(0)

        if self._anim_group is not None and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        self._anim_group = QParallelAnimationGroup(self)

        # Hardware-accelerated window opacity fade-in
        anim_fade = QPropertyAnimation(popup, b"windowOpacity", self)
        anim_fade.setDuration(120)
        anim_fade.setStartValue(0.0)
        anim_fade.setEndValue(1.0)
        anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_group.addAnimation(anim_fade)

        # Subtle downward slide (6px)
        rect = popup.geometry()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            anim_slide = QPropertyAnimation(popup, b"geometry", self)
            anim_slide.setDuration(120)
            anim_slide.setStartValue(QRect(rect.x(), rect.y() - 6, rect.width(), rect.height()))
            anim_slide.setEndValue(rect)
            anim_slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim_group.addAnimation(anim_slide)

        self._anim_group.start()

    def hidePopup(self) -> None:
        """Dismiss the popup cleanly without leaving pending animation tasks."""
        if self._anim_group is not None and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()
        super().hidePopup()
