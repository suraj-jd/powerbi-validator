"""Home / Dashboard page with live Microsoft authentication banner (Stage 3)."""

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

from app.ui.widgets.auth_banner import AuthBanner


class HomePage(QWidget):
    """Dashboard page housing the authentication banner and upcoming Stage 4–13 sections."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("PageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("PageContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(18)

        # Stage 3 Authentication Banner
        self.auth_banner = AuthBanner(container)
        layout.addWidget(self.auth_banner)

        # Header row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(4)

        title_label = QLabel("Power BI Report Health Monitor")
        title_label.setObjectName("PageTitle")
        title_block.addWidget(title_label)

        subtitle_label = QLabel("Validate. Detect. Ensure Data Integrity.")
        subtitle_label.setObjectName("PageSubtitle")
        title_block.addWidget(subtitle_label)

        header_row.addLayout(title_block, stretch=1)

        badge = QLabel("Stage 3 — Auth Ready")
        badge.setObjectName("StageBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)

        # Upcoming stages overview card
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)

        section_title = QLabel("Next Dashboard Milestones")
        section_title.setObjectName("SectionTitle")
        card_layout.addWidget(section_title)

        planned_items = [
            "Power BI workspace & dataset access verification (Stage 4)",
            "Workspace, Report, and Semantic Model registry & CSV/XLSX import (Stage 5)",
            "Refresh status, start/end time, and duration monitoring (Stage 8)",
            "Run summary KPI cards & detailed row-by-row validation results table (Stages 12–13)",
        ]
        items_label = QLabel("\n".join(f"•  {item}" for item in planned_items))
        items_label.setObjectName("BodyText")
        items_label.setWordWrap(True)
        card_layout.addWidget(items_label)

        note_banner = QLabel(
            "Sign in with your organizational Microsoft account above. "
            "Tokens are stored locally using Windows DPAPI encryption and never saved in SQLite."
        )
        note_banner.setObjectName("InfoBanner")
        note_banner.setWordWrap(True)
        card_layout.addWidget(note_banner)

        layout.addWidget(card)
        layout.addStretch(1)

        scroll_area.setWidget(container)
        outer_layout.addWidget(scroll_area)
