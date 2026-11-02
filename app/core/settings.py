"""تنظیمات کاربر: ذخیره‌ی پایدار در دیتابیس با مقادیر پیش‌فرض و نوع‌بندی."""
from __future__ import annotations

import json
from typing import Any

from .database import Database

DEFAULTS: dict[str, Any] = {
    "theme": "system",            # light, dark, system, blue, purple, green, teal, vibrant
    "accent_color": "",           # خالی = رنگ پیش‌فرض تم
    "font_size": 11,
    "editor_font_size": 12,
    "editor_autosave": True,
    "editor_wrap": True,
    "startup_page": "dashboard",  # dashboard, prompts, favorites, last
    "list_show_preview": True,
    "backup_auto_enabled": False,
    "backup_schedule": "daily",   # daily, weekly, on_exit, on_exit_if_changed
    "backup_dir": "",
    "backup_keep": 10,
    "last_auto_backup": "",
    "check_updates": False,       # هیچ ارتباطی بدون اجازه‌ی کاربر
    "update_url": "",             # آدرس صفحه‌ی Releases مخزن خودتان؛ خالی = تنظیم نشده
    "data_changed_since_backup": False,
    "global_search_hotkey": "Ctrl+Shift+Space",
    "last_page": "dashboard",
    "window_geometry": "",
}


class Settings:
    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self._db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return DEFAULTS.get(key, default)
        try:
            return json.loads(row["value"])
        except ValueError:
            return DEFAULTS.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def all(self) -> dict[str, Any]:
        result = dict(DEFAULTS)
        for row in self._db.query("SELECT key, value FROM settings"):
            try:
                result[row["key"]] = json.loads(row["value"])
            except ValueError:
                pass
        return result

    def replace_many(self, values: dict[str, Any]) -> None:
        """برای بازیابی بکاپ: فقط کلیدهای شناخته‌شده پذیرفته می‌شوند."""
        with self._db.transaction():
            for k, v in values.items():
                if k in DEFAULTS:
                    self.set(k, v)
