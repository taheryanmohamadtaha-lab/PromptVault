"""تست‌های بخش‌های مستقل از Qt: میانبر سراسری، تم‌ها، برجسته‌سازی و مسیر ذخیره‌ی داده."""
import json

import pytest

from app.themes.themes import ACCENT_CHOICES, PALETTES, THEME_NAMES, build_qss, is_valid_hex, palette_for, resolve_theme
from app.utils import hotkey, paths
from app.utils.text import highlight_html, normalize


# ---------------------------------------------------------------- میانبر سراسری
@pytest.mark.parametrize("text,expected", [
    ("Ctrl+Shift+Space", (hotkey.MOD_CONTROL | hotkey.MOD_SHIFT, 0x20)),
    ("ctrl+alt+k", (hotkey.MOD_CONTROL | hotkey.MOD_ALT, ord("K"))),
    ("Alt+F9", (hotkey.MOD_ALT, 0x78)),
    ("Ctrl+7", (hotkey.MOD_CONTROL, ord("7"))),
    ("Win+Q", (hotkey.MOD_WIN, ord("Q"))),
])
def test_parse_hotkey_valid(text, expected):
    assert hotkey.parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["", "A", "Space", "Shift+A", "Ctrl", "Ctrl+Shift", "Ctrl+A+B", "Ctrl+F13", "Ctrl+ب"])
def test_parse_hotkey_invalid(text):
    # تنها Shift یا حرف بدون Ctrl/Alt/Win با تایپ عادی تداخل می‌کند و پذیرفته نمی‌شود
    assert hotkey.parse_hotkey(text) is None


def test_register_is_safe_off_windows():
    g = hotkey.GlobalHotkey(lambda: None)
    if not g.supported():
        assert g.register("Ctrl+Shift+Space") is False
    g.unregister()  # نباید خطا بدهد


# ---------------------------------------------------------------- تم‌ها
def test_all_required_themes_exist():
    required = {"light", "dark", "system", "blue", "purple", "green", "teal", "vibrant"}
    assert required <= set(THEME_NAMES)
    assert set(PALETTES) | {"system"} >= required


@pytest.mark.parametrize("theme", list(THEME_NAMES))
def test_every_theme_builds_qss(theme):
    for dark in (False, True):
        pal = palette_for(theme, "", dark)
        qss = build_qss(pal, 11)
        assert pal["accent"] in qss and "QPushButton" in qss
        assert "None" not in qss


def test_system_theme_follows_os():
    assert resolve_theme("system", True) == "dark"
    assert resolve_theme("system", False) == "light"
    assert resolve_theme("not-a-theme") == "light"


def test_accent_override_and_validation():
    pal = palette_for("light", "#ff0000")
    assert pal["accent"] == "#FF0000" and pal["on_accent"] in ("#FFFFFF", "#101326")
    assert palette_for("light", "not-a-color")["accent"] == PALETTES["light"]["accent"]
    assert all(is_valid_hex(c) for c in ACCENT_CHOICES)
    assert not is_valid_hex("#12345") and not is_valid_hex("#GGGGGG")


def test_theme_and_accent_survive_restart(tmp_path):
    from app.core.context import AppContext
    c1 = AppContext(tmp_path / "d")
    c1.settings.set("theme", "purple")
    c1.settings.set("accent_color", "#FF7A1A")
    c1.close()
    c2 = AppContext(tmp_path / "d")
    assert c2.settings.get("theme") == "purple" and c2.settings.get("accent_color") == "#FF7A1A"
    c2.close()


# ---------------------------------------------------------------- متن
def test_highlight_is_html_safe_and_persian_aware():
    out = highlight_html("ساخت <b>اندیکاتور</b> MT5", "اندیکاتور mt5")
    assert "&lt;b&gt;" in out and "<b>" not in out
    assert out.count("background-color") == 2
    # ی/ک عربی و ارقام فارسی یکسان دیده می‌شوند
    assert normalize("كتاب ۱۲۳ يك") == "کتاب 123 یک"
    assert "background-color" in highlight_html("کتاب", "كتاب")


# ---------------------------------------------------------------- مسیر داده
def test_data_dir_choice_is_remembered(tmp_path, monkeypatch):
    monkeypatch.delenv("PROMPTVAULT_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert paths.get_data_dir() == tmp_path / "local" / "PromptVault" / "data"
    custom = tmp_path / "my data"
    paths.set_data_dir(custom)
    assert paths.get_data_dir() == custom
    paths.set_data_dir(None)
    assert paths.get_data_dir() == paths.default_data_dir()
    # فایل راه‌انداز خراب، برنامه را از کار نمی‌اندازد
    (tmp_path / "appdata" / "PromptVault" / "bootstrap.json").write_text("{خراب", encoding="utf-8")
    assert paths.get_data_dir() == paths.default_data_dir()
    json.loads('{"ok": 1}')
