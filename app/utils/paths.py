"""مسیرهای برنامه: پوشه‌ی داده، پوشه‌ی منابع و فایل راه‌انداز (برای تغییر مسیر ذخیره‌سازی)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

APP_NAME = "PromptVault"


def now_iso() -> str:
    """زمان محلی با دقت ثانیه، قابل مرتب‌سازی."""
    return datetime.now().isoformat(timespec="seconds")


def config_dir() -> Path:
    """پوشه‌ی ثابت تنظیمات راه‌انداز (جدا از پوشه‌ی داده)."""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME / "data"
    return Path.home() / ".local" / "share" / APP_NAME / "data"


def _bootstrap_file() -> Path:
    return config_dir() / "bootstrap.json"


def get_data_dir() -> Path:
    """مسیر داده‌ی فعلی: اگر کاربر مسیر دلخواه تعیین کرده باشد همان، وگرنه پیش‌فرض."""
    env = os.environ.get("PROMPTVAULT_DATA_DIR")
    if env:
        return Path(env)
    try:
        data = json.loads(_bootstrap_file().read_text(encoding="utf-8"))
        custom = data.get("data_dir")
        if custom:
            return Path(custom)
    except (OSError, ValueError):
        pass
    return default_data_dir()


def set_data_dir(path: str | Path | None) -> None:
    """مسیر جدید ذخیره‌سازی را برای اجرای بعدی برنامه ثبت می‌کند (None = پیش‌فرض)."""
    f = _bootstrap_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"data_dir": str(path) if path else ""}, ensure_ascii=False), encoding="utf-8")


def resource_path(*parts: str) -> Path:
    """مسیر فایل‌های همراه برنامه، هم در حالت سورس و هم در EXE ساخته‌شده با PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base.joinpath(*parts)
