"""میانبر سراسری (کار می‌کند حتی وقتی برنامه در پس‌زمینه است) — فقط ویندوز.

تحلیل رشته‌ی میانبر (parse_hotkey) کاملاً مستقل از Qt و ویندوز است و تست می‌شود.
ثبت واقعی میانبر با RegisterHotKey ویندوز انجام می‌شود و در صورت هر مشکلی بی‌صدا شکست می‌خورد
(در این حالت میانبر داخل برنامه، Ctrl+K، همچنان کار می‌کند).
"""
from __future__ import annotations

import sys
from typing import Callable

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
         "win": MOD_WIN, "meta": MOD_WIN}
_NAMED = {"space": 0x20, "tab": 0x09, "return": 0x0D, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B}


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Ctrl+Shift+Space' ← (modifiers, virtual_key). اگر نامعتبر بود None.
    حداقل یک کلید تغییردهنده (Ctrl/Alt/Win) لازم است تا با تایپ عادی تداخل نکند."""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if len(parts) < 2:
        return None
    mods, key = 0, None
    for p in parts:
        if p in _MODS:
            mods |= _MODS[p]
        elif key is None:
            key = p
        else:
            return None
    if key is None or not (mods & (MOD_CONTROL | MOD_ALT | MOD_WIN)):
        return None
    if key in _NAMED:
        vk = _NAMED[key]
    elif len(key) == 1 and key.isalpha() and key.isascii():
        vk = ord(key.upper())
    elif len(key) == 1 and key.isdigit():
        vk = ord(key)
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
    else:
        return None
    return mods, vk


def make_filter(callback: Callable[[], None]):
    """ساخت فیلتر رویداد بومی Qt برای WM_HOTKEY. فقط روی ویندوز و با نصب PySide6 معنا دارد."""
    from PySide6.QtCore import QAbstractNativeEventFilter

    class _Filter(QAbstractNativeEventFilter):
        def __init__(self):
            super().__init__()
            self.hotkey_id = 0xB001
            self.registered = False

        def nativeEventFilter(self, event_type, message):  # noqa: N802
            if not self.registered:
                return False, 0
            try:
                if bytes(event_type) == b"windows_generic_MSG":
                    from ctypes import wintypes
                    msg = wintypes.MSG.from_address(int(message))
                    if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                        callback()
                        return True, 0
            except Exception:  # هرگز نباید حلقه‌ی رویداد را خراب کند
                pass
            return False, 0

    return _Filter()


class GlobalHotkey:
    def __init__(self, callback: Callable[[], None]):
        self._filter = None
        self._callback = callback
        self.active = False

    @staticmethod
    def supported() -> bool:
        return sys.platform == "win32"

    def register(self, text: str) -> bool:
        self.unregister()
        if not self.supported():
            return False
        parsed = parse_hotkey(text)
        if parsed is None:
            return False
        try:
            import ctypes
            from PySide6.QtCore import QCoreApplication
            if self._filter is None:
                self._filter = make_filter(self._callback)
                QCoreApplication.instance().installNativeEventFilter(self._filter)
            mods, vk = parsed
            ok = bool(ctypes.windll.user32.RegisterHotKey(None, self._filter.hotkey_id, mods | MOD_NOREPEAT, vk))
            self._filter.registered = ok
            self.active = ok
            return ok
        except Exception:
            self.active = False
            return False

    def unregister(self) -> None:
        if self._filter is not None and self.active:
            try:
                import ctypes
                ctypes.windll.user32.UnregisterHotKey(None, self._filter.hotkey_id)
            except Exception:
                pass
            self._filter.registered = False
        self.active = False
