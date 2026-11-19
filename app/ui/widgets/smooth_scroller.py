"""Smooth deceleration scrolling utility for Qt QAbstractScrollArea and item views."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractItemView, QAbstractScrollArea, QScrollBar


class SmoothScrollFilter(QObject):
    """Event filter providing smooth animated deceleration for mouse wheel scrolling.

    - Respects high-precision touchpads by passing fractional pixel events directly to Qt.
    - Interpolates discrete notched mouse wheel ticks with a smooth 130ms OutCubic animation.
    - Accumulates rapid wheel ticks smoothly to prevent jerky stutter.
    """

    def __init__(self, scroll_area: QAbstractScrollArea, parent: QObject | None = None) -> None:
        super().__init__(parent or scroll_area)
        self._scroll_area = scroll_area
        self._v_bar: QScrollBar = scroll_area.verticalScrollBar()
        self._anim = QPropertyAnimation(self._v_bar, b"value", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setDuration(130)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            wheel_event: QWheelEvent = event  # type: ignore[assignment]
            # Precision touchpad: let Qt scroll natively with hardware pixel deltas
            if not wheel_event.pixelDelta().isNull():
                return False

            delta_y = wheel_event.angleDelta().y()
            if delta_y != 0:
                steps = -delta_y / 120.0
                step_size = max(self._v_bar.singleStep(), 22)
                base = (
                    self._anim.endValue()
                    if self._anim.state() == QPropertyAnimation.State.Running
                    else self._v_bar.value()
                )
                target = int(base + (steps * step_size * 2))
                target = max(self._v_bar.minimum(), min(self._v_bar.maximum(), target))

                if target != self._v_bar.value():
                    self._anim.stop()
                    self._anim.setStartValue(self._v_bar.value())
                    self._anim.setEndValue(target)
                    self._anim.start()
                    return True
        return super().eventFilter(watched, event)


def apply_smooth_scrolling(scroll_area: QAbstractScrollArea) -> SmoothScrollFilter:
    """Configure smooth per-pixel scrolling and install deceleration wheel filter."""
    if isinstance(scroll_area, QAbstractItemView):
        scroll_area.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        scroll_area.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    scroll_area.verticalScrollBar().setSingleStep(20)
    scroll_area.horizontalScrollBar().setSingleStep(20)

    filt = SmoothScrollFilter(scroll_area)
    scroll_area.viewport().installEventFilter(filt)
    return filt
