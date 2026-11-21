"""Dialog for configuring Microsoft Teams alerts with the signed-in Microsoft account."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.auth.msal_auth import AuthAccount
from app.services.teams_alert_service import TeamsAlertConfig, TeamsAlertService

logger = logging.getLogger(__name__)


class TeamsToggleSwitch(QCheckBox):
    """Custom graphical ON/OFF toggle switch with green/red indicator pill."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(58, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self, pos: QPoint) -> bool:
        """Allow clicking anywhere on the full 58x28 switch capsule."""
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        checked = self.isChecked()
        enabled = self.isEnabled()

        if not enabled:
            bg_color = QColor("#CBD5E1")
        elif checked:
            bg_color = QColor("#16A34A")  # Vibrant Green when ON
        else:
            bg_color = QColor("#DC2626")  # Vibrant Red when OFF

        # Outer capsule
        p.setBrush(QBrush(bg_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, 58, 28, 14, 14)

        # ON / OFF Label
        p.setPen(QPen(QColor("#FFFFFF")))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(font)
        if checked:
            p.drawText(QRectF(8, 0, 26, 28), Qt.AlignmentFlag.AlignCenter, "ON")
            knob_x = 58 - 25
        else:
            p.drawText(QRectF(24, 0, 28, 28), Qt.AlignmentFlag.AlignCenter, "OFF")
            knob_x = 3

        # Circular sliding knob
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(knob_x, 3, 22, 22)
        p.end()


class TeamsAlertConfigDialog(QDialog):
    """Configuration dialog for Microsoft Teams validation alert notifications."""

    def __init__(
        self,
        teams_service: TeamsAlertService,
        account: AuthAccount | None = None,
        signin_callback: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._teams_service = teams_service
        self._account = account
        self._signin_callback = signin_callback
        self._config = teams_service.config

        self.setWindowTitle("Microsoft Teams Alert Settings")
        self.setMinimumWidth(720)
        self.resize(740, 540)

        self._build_ui()
        self._apply_initial_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 1. Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("Microsoft Teams Validation Alerts")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #0F172A;")
        title_box.addWidget(lbl_title)

        lbl_sub = QLabel(
            "Receive real-time notification cards in Microsoft Teams whenever validation checks evaluate."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B;")
        title_box.addWidget(lbl_sub)
        header_row.addLayout(title_box, stretch=1)

        # Account status pill in top right
        self.account_pill = QFrame()
        self.account_pill_lay = QHBoxLayout(self.account_pill)
        self.account_pill_lay.setContentsMargins(10, 5, 10, 5)
        self.account_pill_lay.setSpacing(6)

        self.lbl_account_icon = QLabel()
        self.account_pill_lay.addWidget(self.lbl_account_icon)

        self.lbl_account_text = QLabel()
        self.account_pill_lay.addWidget(self.lbl_account_text)
        header_row.addWidget(self.account_pill, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        self._update_account_banner()

        # 2. Master Toggle Row (Green/Red ON-OFF Switch)
        self.toggle_card = QFrame()
        self.toggle_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 7px; padding: 6px 12px; } "
            "QFrame:hover { border-color: #CBD5E1; }"
        )
        t_lay = QHBoxLayout(self.toggle_card)
        t_lay.setContentsMargins(2, 2, 2, 2)
        t_lay.setSpacing(12)

        self.chk_enabled = TeamsToggleSwitch()
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        t_lay.addWidget(self.chk_enabled)

        lbl_toggle_title = QLabel("Keep Teams validation alerts active")
        lbl_toggle_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        lbl_toggle_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        t_lay.addWidget(lbl_toggle_title)

        lbl_toggle_sub = QLabel("(Delivers rich report cards into your Teams channel or chat)")
        lbl_toggle_sub.setStyleSheet("font-size: 11px; color: #64748B;")
        lbl_toggle_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        t_lay.addWidget(lbl_toggle_sub)
        t_lay.addStretch(1)

        self.toggle_card.mousePressEvent = self._on_toggle_card_clicked
        layout.addWidget(self.toggle_card)

        # 3. Settings Card (Active or Grayed-Out)
        self.settings_card = QFrame()
        self.settings_card.setObjectName("SettingsCard")
        s_lay = QVBoxLayout(self.settings_card)
        s_lay.setContentsMargins(16, 14, 16, 14)
        s_lay.setSpacing(12)

        # Mode Selection Row
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)

        lbl_mode = QLabel("Delivery Mode:")
        lbl_mode.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        mode_row.addWidget(lbl_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Teams Channel Webhook / Workflow (Instant & Zero Admin Required)", "webhook")
        self.combo_mode.addItem("Direct Microsoft Graph API (Uses Signed-In Microsoft Account)", "graph")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.combo_mode, stretch=1)
        s_lay.addLayout(mode_row)

        # Webhook Container
        self.webhook_container = QWidget()
        w_lay = QVBoxLayout(self.webhook_container)
        w_lay.setContentsMargins(0, 0, 0, 0)
        w_lay.setSpacing(6)

        lbl_url = QLabel("Teams Channel Webhook URL:")
        lbl_url.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        w_lay.addWidget(lbl_url)

        self.edit_webhook_url = QLineEdit()
        self.edit_webhook_url.setPlaceholderText("https://...webhook.office.com/... or https://...logic.azure.com/...")
        self.edit_webhook_url.setStyleSheet(
            "QLineEdit { border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 10px; font-size: 12px; } "
            "QLineEdit:focus { border-color: #1668DC; }"
        )
        w_lay.addWidget(self.edit_webhook_url)

        # Helpful instructions box
        self.guide_box = QFrame()
        self.guide_box.setStyleSheet(
            "QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; } "
            "QLabel { background: transparent; border: none; font-size: 11px; color: #475569; }"
        )
        g_lay = QVBoxLayout(self.guide_box)
        g_lay.setContentsMargins(0, 0, 0, 0)
        g_lay.setSpacing(3)
        lbl_g_title = QLabel("💡 How to connect any Microsoft Teams channel (No IT Admin required):")
        lbl_g_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #0284C7;")
        g_lay.addWidget(lbl_g_title)
        g_lay.addWidget(QLabel("1. In Microsoft Teams, right-click your target channel and choose 'Workflows'."))
        g_lay.addWidget(QLabel("2. Select 'Post to a channel when a webhook request is received'."))
        g_lay.addWidget(QLabel("3. Click Next, copy the generated Webhook URL, and paste it into the field above."))
        w_lay.addWidget(self.guide_box)

        s_lay.addWidget(self.webhook_container)

        # Graph API Container
        self.graph_container = QWidget()
        gr_lay = QVBoxLayout(self.graph_container)
        gr_lay.setContentsMargins(0, 0, 0, 0)
        gr_lay.setSpacing(6)

        lbl_gr_info = QLabel("Microsoft Graph Chat / Channel ID:")
        lbl_gr_info.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        gr_lay.addWidget(lbl_gr_info)

        self.edit_graph_chat_id = QLineEdit()
        self.edit_graph_chat_id.setPlaceholderText("19:meeting_... or Teams Chat ID")
        self.edit_graph_chat_id.setStyleSheet(
            "QLineEdit { border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 10px; font-size: 12px; }"
        )
        gr_lay.addWidget(self.edit_graph_chat_id)

        lbl_gr_note = QLabel(
            "Note: Posting via Microsoft Graph requires delegated 'Chat.ReadWrite' or 'ChannelMessage.Send' "
            "permissions in your Microsoft Entra App registration. If your tenant restricts this, switch to Webhook mode."
        )
        lbl_gr_note.setWordWrap(True)
        lbl_gr_note.setStyleSheet("font-size: 11px; color: #D97706; font-style: italic;")
        gr_lay.addWidget(lbl_gr_note)

        s_lay.addWidget(self.graph_container)

        # Trigger Criteria & Details Row
        opt_row = QHBoxLayout()
        opt_row.setSpacing(14)

        lbl_trigger = QLabel("Send Alerts:")
        lbl_trigger.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        opt_row.addWidget(lbl_trigger)

        self.combo_notify_on = QComboBox()
        self.combo_notify_on.addItem("Only on Failures & Warnings (Recommended)", "failure_only")
        self.combo_notify_on.addItem("Only on Critical Failures", "failure_strict")
        self.combo_notify_on.addItem("On Every Validation Run (All Results)", "all")
        opt_row.addWidget(self.combo_notify_on)

        opt_row.addStretch(1)

        self.chk_details = QCheckBox("Include failed check breakdown in card")
        self.chk_details.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        opt_row.addWidget(self.chk_details)

        s_lay.addLayout(opt_row)

        # Test Alert Action Bar
        test_bar = QHBoxLayout()
        test_bar.setSpacing(10)

        self.btn_test = QPushButton("🚀  Send Test Alert")
        self.btn_test.setObjectName("SecondaryButton")
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.setStyleSheet("font-weight: 600; font-size: 12px; padding: 6px 14px;")
        self.btn_test.clicked.connect(self._on_send_test_alert)
        test_bar.addWidget(self.btn_test)

        self.lbl_test_result = QLabel()
        self.lbl_test_result.setWordWrap(True)
        test_bar.addWidget(self.lbl_test_result, stretch=1)

        s_lay.addLayout(test_bar)
        layout.addWidget(self.settings_card)

        # 4. Footer Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(
            "background-color: #1668DC; color: #FFFFFF; font-weight: 700; font-size: 13px; "
            "padding: 7px 20px; border-radius: 6px;"
        )
        self.btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    def _update_account_banner(self) -> None:
        """Render the status of the logged-in Microsoft account."""
        if self._account and self._account.username:
            self.account_pill.setStyleSheet(
                "QFrame { background-color: #DCFCE7; border: 1px solid #BBF7D0; border-radius: 6px; padding: 4px 10px; }"
            )
            self.lbl_account_icon.setText("✓")
            self.lbl_account_icon.setStyleSheet("font-size: 12px; font-weight: 700; color: #15803D;")
            self.lbl_account_text.setText(f"Connected: {self._account.username}")
            self.lbl_account_text.setStyleSheet("font-size: 11px; font-weight: 600; color: #15803D;")
            self.account_pill.setToolTip(
                f"Signed-in user: {self._account.display_name} ({self._account.username})\n"
                "Teams alert cards will be attributed to this Microsoft account."
            )
        else:
            self.account_pill.setStyleSheet(
                "QFrame { background-color: #FEF3C7; border: 1px solid #FDE68A; border-radius: 6px; padding: 4px 10px; }"
            )
            self.lbl_account_icon.setText("⚠")
            self.lbl_account_icon.setStyleSheet("font-size: 12px; font-weight: 700; color: #B45309;")
            self.lbl_account_text.setText("Sign in to link account")
            self.lbl_account_text.setStyleSheet("font-size: 11px; font-weight: 600; color: #B45309;")
            self.account_pill.setToolTip(
                "Sign in with Microsoft from the Home page to link your Teams account identity."
            )

    def _apply_initial_state(self) -> None:
        """Populate controls from stored config."""
        self.chk_enabled.setChecked(self._config.enabled)

        # Mode
        mode_idx = self.combo_mode.findData(self._config.delivery_mode)
        if mode_idx >= 0:
            self.combo_mode.setCurrentIndex(mode_idx)

        self.edit_webhook_url.setText(self._config.webhook_url)
        self.edit_graph_chat_id.setText(self._config.graph_chat_id)

        # Notify on
        notif_idx = self.combo_notify_on.findData(self._config.notify_on)
        if notif_idx >= 0:
            self.combo_notify_on.setCurrentIndex(notif_idx)

        self.chk_details.setChecked(self._config.include_rule_details)

        self._on_mode_changed(self.combo_mode.currentIndex())
        self._on_enabled_toggled(self.chk_enabled.isChecked())

    def _on_toggle_card_clicked(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.chk_enabled.isEnabled():
            self.chk_enabled.toggle()
        event.accept()

    def _on_mode_changed(self, idx: int) -> None:
        mode = self.combo_mode.itemData(idx)
        is_webhook = (mode == "webhook")
        self.webhook_container.setVisible(is_webhook)
        self.graph_container.setVisible(not is_webhook)

    def _on_enabled_toggled(self, enabled: bool) -> None:
        self.settings_card.setEnabled(enabled)

        if enabled:
            self.settings_card.setStyleSheet(
                "QFrame#SettingsCard { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; } "
                "QLabel { color: #334155; font-size: 12px; font-weight: 600; }"
            )
            self.guide_box.setStyleSheet(
                "QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; } "
                "QLabel { background: transparent; border: none; font-size: 11px; color: #475569; }"
            )
        else:
            self.settings_card.setStyleSheet(
                "QFrame#SettingsCard { background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 8px; } "
                "QLabel { color: #94A3B8; font-size: 12px; font-weight: 600; } "
                "QLineEdit { background-color: #E2E8F0; color: #94A3B8; border-color: #CBD5E1; } "
                "QComboBox { background-color: #E2E8F0; color: #94A3B8; border-color: #CBD5E1; } "
                "QPushButton { background-color: #E2E8F0; color: #94A3B8; border-color: #CBD5E1; }"
            )
            self.guide_box.setStyleSheet(
                "QFrame { background-color: #E2E8F0; border: 1px solid #CBD5E1; border-radius: 6px; padding: 8px 12px; } "
                "QLabel { background: transparent; border: none; font-size: 11px; color: #94A3B8; }"
            )

        self.chk_enabled.update()

    def _build_current_config(self) -> TeamsAlertConfig:
        return TeamsAlertConfig(
            enabled=self.chk_enabled.isChecked(),
            delivery_mode=self.combo_mode.currentData(),
            webhook_url=self.edit_webhook_url.text().strip(),
            notify_on=self.combo_notify_on.currentData(),
            include_rule_details=self.chk_details.isChecked(),
            graph_chat_id=self.edit_graph_chat_id.text().strip(),
        )

    def _on_send_test_alert(self) -> None:
        """Dispatch a sample alert immediately to test the configured Teams connection."""
        cfg = self._build_current_config()
        if cfg.delivery_mode == "webhook" and not cfg.webhook_url:
            self.lbl_test_result.setText("⚠ Please enter a Teams Webhook URL first.")
            self.lbl_test_result.setStyleSheet("color: #B45309; font-size: 11px; font-weight: 600;")
            return

        self.btn_test.setEnabled(False)
        self.lbl_test_result.setText("⏳ Sending test alert card to Microsoft Teams...")
        self.lbl_test_result.setStyleSheet("color: #0284C7; font-size: 11px; font-weight: 600;")

        # Temporarily use current UI config for test
        original_cfg = self._teams_service.config
        self._teams_service._config = cfg

        def _on_done(success: bool, msg: str) -> None:
            self.btn_test.setEnabled(True)
            self._teams_service._config = original_cfg
            if success:
                self.lbl_test_result.setText(f"✓ {msg}")
                self.lbl_test_result.setStyleSheet("color: #15803D; font-size: 11px; font-weight: 600;")
            else:
                self.lbl_test_result.setText(f"✕ {msg}")
                self.lbl_test_result.setStyleSheet("color: #B91C1C; font-size: 11px; font-weight: 600;")

        self._teams_service.send_alert_async(
            summary=None,  # Service creates sample test summary when is_test=True
            account=self._account,
            is_test=True,
            on_completed=_on_done,
        )

    def _save_settings(self) -> None:
        cfg = self._build_current_config()
        self._teams_service.save_config(cfg)
        self.accept()
