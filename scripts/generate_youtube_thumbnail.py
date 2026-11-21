"""Generate a professional, high-resolution 1280x720 YouTube video thumbnail for Power BI Validation Tool."""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

WIDTH = 1280
HEIGHT = 720


def create_thumbnail() -> Path:
    # Need a minimal QGuiApplication for font/graphics rendering
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv)

    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#0B132B"))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    # 1. Dark Tech Radial / Linear Gradient Background
    bg_gradient = QLinearGradient(0, 0, WIDTH, HEIGHT)
    bg_gradient.setColorAt(0.0, QColor("#0A0F1D"))
    bg_gradient.setColorAt(0.4, QColor("#0F172A"))
    bg_gradient.setColorAt(0.8, QColor("#1E293B"))
    bg_gradient.setColorAt(1.0, QColor("#0F2942"))
    painter.fillRect(0, 0, WIDTH, HEIGHT, bg_gradient)

    # Accent glow top-right
    top_glow = QLinearGradient(WIDTH - 300, 0, WIDTH, 400)
    top_glow.setColorAt(0.0, QColor(22, 104, 220, 60))
    top_glow.setColorAt(1.0, QColor(245, 158, 11, 0))
    painter.fillRect(WIDTH - 500, 0, 500, 400, top_glow)

    # Accent glow bottom-left
    bot_glow = QLinearGradient(0, HEIGHT - 300, 400, HEIGHT)
    bot_glow.setColorAt(0.0, QColor(245, 158, 11, 40))
    bot_glow.setColorAt(1.0, QColor(16, 185, 129, 0))
    painter.fillRect(0, HEIGHT - 350, 450, 350, bot_glow)

    # 2. Left Side: Typography & Value Proposition
    left_x = 60
    top_y = 65

    # Top Tag: "ENTERPRISE QUALITY ASSURANCE"
    tag_path = QPainterPath()
    tag_path.addRoundedRect(QRectF(left_x, top_y, 350, 34), 6, 6)
    painter.fillPath(tag_path, QColor(30, 41, 59, 220))
    painter.strokePath(tag_path, QPen(QColor("#F59E0B"), 1.5))

    painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
    painter.setPen(QColor("#F59E0B"))
    painter.drawText(
        QRectF(left_x, top_y, 350, 34),
        Qt.AlignmentFlag.AlignCenter,
        "★  ENTERPRISE QUALITY ASSURANCE",
    )

    # Main Headline Part 1: "AUTOMATE YOUR"
    painter.setFont(QFont("Segoe UI", 32, QFont.Weight.Black))
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(left_x, top_y + 85, "AUTOMATE YOUR")

    # Main Headline Part 2: "POWER BI AUDITS" (Gold / Amber)
    painter.setFont(QFont("Segoe UI", 42, QFont.Weight.Black))
    painter.setPen(QColor("#F59E0B"))
    painter.drawText(left_x, top_y + 150, "POWER BI AUDITS")

    # High-Impact Value Badge: "SAVE 2-3 HOURS DAILY"
    badge_y = top_y + 185
    badge_path = QPainterPath()
    badge_path.addRoundedRect(QRectF(left_x, badge_y, 380, 48), 8, 8)
    badge_grad = QLinearGradient(left_x, badge_y, left_x + 380, badge_y + 48)
    badge_grad.setColorAt(0.0, QColor("#1668DC"))
    badge_grad.setColorAt(1.0, QColor("#0284C7"))
    painter.fillPath(badge_path, badge_grad)
    painter.strokePath(badge_path, QPen(QColor("#38BDF8"), 1.5))

    painter.setFont(QFont("Segoe UI", 18, QFont.Weight.ExtraBold))
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(
        QRectF(left_x, badge_y, 380, 48),
        Qt.AlignmentFlag.AlignCenter,
        "⚡  SAVE 2-3 HOURS DAILY",
    )

    # Sub-bullets: What it checks
    features = [
        ("✓ Scheduled Refresh SLA (Pass / Fail / Duration)", "#10B981"),
        ("✓ Deep Data Checks: Nulls, Duplicates, Row Counts", "#38BDF8"),
        ("✓ DAX Measures & Anomaly Baseline Deviations", "#F59E0B"),
        ("✓ Side-by-Side Run Comparison & Regressions", "#A855F7"),
    ]

    feat_y = badge_y + 80
    painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    for text, color_hex in features:
        # Bullet background bar
        bar_path = QPainterPath()
        bar_path.addRoundedRect(QRectF(left_x, feat_y - 20, 480, 32), 6, 6)
        painter.fillPath(bar_path, QColor(15, 23, 42, 190))
        painter.strokePath(bar_path, QPen(QColor(color_hex), 1.0))

        painter.setPen(QColor(color_hex))
        painter.drawText(QRectF(left_x + 14, feat_y - 20, 460, 32), Qt.AlignmentFlag.AlignVCenter, text)
        feat_y += 44

    # Bottom Zero-Trust Badge
    bot_y = HEIGHT - 85
    bot_path = QPainterPath()
    bot_path.addRoundedRect(QRectF(left_x, bot_y, 440, 38), 6, 6)
    painter.fillPath(bot_path, QColor(6, 78, 59, 160))
    painter.strokePath(bot_path, QPen(QColor("#10B981"), 1.2))

    painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
    painter.setPen(QColor("#34D399"))
    painter.drawText(
        QRectF(left_x, bot_y, 440, 38),
        Qt.AlignmentFlag.AlignCenter,
        "🔒  100% Local-First & Zero-Trust (Windows DPAPI)",
    )

    # 3. Right Side: Floating App Screenshot with Shadow and Glowing Frame
    dash_path = Path("docs/screenshots/01_dashboard_home.png")
    if dash_path.exists():
        pm_dash = QPixmap(str(dash_path))
        # Scale to fit nicely on the right half
        scaled_w = 640
        scaled_h = int(pm_dash.height() * (scaled_w / pm_dash.width()))
        pm_scaled = pm_dash.scaled(scaled_w, scaled_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        rx = WIDTH - scaled_w - 40
        ry = (HEIGHT - scaled_h) // 2

        # Outer Shadow Card
        shadow_rect = QRectF(rx - 8, ry - 8, pm_scaled.width() + 16, pm_scaled.height() + 16)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, 12, 12)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 140))
        painter.strokePath(shadow_path, QPen(QColor(22, 104, 220, 180), 2.0))

        # Clip image with rounded corners
        img_rect = QRectF(rx, ry, pm_scaled.width(), pm_scaled.height())
        clip_path = QPainterPath()
        clip_path.addRoundedRect(img_rect, 10, 10)

        painter.save()
        painter.setClipPath(clip_path)
        painter.drawPixmap(int(rx), int(ry), pm_scaled)
        painter.restore()

        # Floating Pill on top of screenshot
        pill_w = 260
        pill_h = 42
        pill_x = rx + (pm_scaled.width() - pill_w) // 2
        pill_y = ry + pm_scaled.height() - 28

        p_path = QPainterPath()
        p_path.addRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 8, 8)
        painter.fillPath(p_path, QColor(15, 23, 42, 240))
        painter.strokePath(p_path, QPen(QColor("#F59E0B"), 1.8))

        painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            QRectF(pill_x, pill_y, pill_w, pill_h),
            Qt.AlignmentFlag.AlignCenter,
            "▶  COMPLETE SOFTWARE TOUR",
        )

    painter.end()

    out_file = Path("docs/youtube_thumbnail.png")
    image.save(str(out_file), "PNG")
    print(f"[✓] Saved 1280x720 YouTube thumbnail to {out_file}")
    return out_file


if __name__ == "__main__":
    create_thumbnail()
