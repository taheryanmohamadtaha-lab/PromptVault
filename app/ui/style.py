"""اعمال تم و رنگ تأکیدی روی کل برنامه (بدون نیاز به راه‌اندازی مجدد)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ..core.settings import Settings
from ..themes.themes import build_qss, palette_for


def system_is_dark(app: QApplication) -> bool:
    try:  # Qt 6.5 به بعد
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply_theme(app: QApplication, settings: Settings) -> dict:
    """تم + رنگ تأکیدی + اندازه‌ی فونت را از تنظیمات می‌خواند و اعمال می‌کند. پالت رنگی را برمی‌گرداند."""
    theme = settings.get("theme") or "system"
    accent = settings.get("accent_color") or ""
    try:
        size = max(8, min(20, int(settings.get("font_size") or 11)))
    except (TypeError, ValueError):
        size = 11
    pal = palette_for(theme, accent, system_is_dark(app))
    app.setStyleSheet(build_qss(pal, size))
    return pal
