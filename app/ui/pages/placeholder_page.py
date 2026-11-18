"""Reusable scrollable placeholder page for Stage 0."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PlaceholderPage(QWidget):
    """Scrollable light-enterprise page with a title header and Stage 0 card."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        planned_items: list[str],
        stage_note: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._build_ui(title, subtitle, planned_items, stage_note)

    def _build_ui(
        self,
        title: str,
        subtitle: str,
        planned_items: list[str],
        stage_note: str,
    ) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("PageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("PageContainer")
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(18)

        # Header row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        title_block.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)
        title_block.addWidget(subtitle_label)

        header_row.addLayout(title_block, stretch=1)

        badge = QLabel("Stage 0 Placeholder")
        badge.setObjectName("StageBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

        content_layout.addLayout(header_row)

        # Overview card
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)

        section_title = QLabel("Planned for Upcoming Stages")
        section_title.setObjectName("SectionTitle")
        card_layout.addWidget(section_title)

        bullet_lines = "\n".join(f"•  {item}" for item in planned_items)
        items_label = QLabel(bullet_lines)
        items_label.setObjectName("BodyText")
        items_label.setWordWrap(True)
        items_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(items_label)

        note_banner = QLabel(stage_note)
        note_banner.setObjectName("InfoBanner")
        note_banner.setWordWrap(True)
        card_layout.addWidget(note_banner)

        content_layout.addWidget(card)
        content_layout.addStretch(1)

        scroll_area.setWidget(container)
        outer_layout.addWidget(scroll_area)
