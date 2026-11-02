"""تم‌ها و تولید QSS. هیچ وابستگی به Qt ندارد (قابل تست)."""
from __future__ import annotations

THEME_NAMES = {
    "system": "خودکار (مطابق ویندوز)",
    "light": "روشن",
    "dark": "تاریک",
    "blue": "آبی مدرن",
    "purple": "بنفش",
    "green": "سبز",
    "teal": "فیروزه‌ای",
    "vibrant": "رنگی و پرانرژی",
}

# bg: پس‌زمینه‌ی صفحه | surface: کارت‌ها | sidebar: نوار کناری
_LIGHT = dict(
    bg="#F4F6FB", surface="#FFFFFF", surface2="#EEF1F8", border="#DDE2EE",
    text="#1B2033", muted="#6B7390", accent="#4F6BED", on_accent="#FFFFFF",
    danger="#E5484D", success="#2FA66A", warn="#E8A33D",
    sidebar="#FFFFFF", sidebar_text="#39415C", sidebar_hover="#EEF1F8", sidebar_sel_text="#FFFFFF",
    sidebar_bg_extra="", scroll="#C4CADB",
)
_DARK = dict(
    bg="#0F1220", surface="#181C2F", surface2="#20253B", border="#2B3150",
    text="#E8EBF7", muted="#8F97B8", accent="#7C8CFF", on_accent="#0B0E1B",
    danger="#FF6B70", success="#4CD08B", warn="#F2B84B",
    sidebar="#12152A", sidebar_text="#B8BFDD", sidebar_hover="#1D2240", sidebar_sel_text="#0B0E1B",
    sidebar_bg_extra="", scroll="#3A4166",
)

PALETTES: dict[str, dict] = {
    "light": _LIGHT,
    "dark": _DARK,
    "blue": {**_LIGHT, "bg": "#EAF2FF", "surface": "#FFFFFF", "surface2": "#DCE9FF", "border": "#C5D9F7",
             "accent": "#1E6BFF", "sidebar": "#0B3D91", "sidebar_text": "#D6E4FF", "sidebar_hover": "#1550B8",
             "sidebar_sel_text": "#0B3D91", "text": "#0F2547", "muted": "#58729B", "scroll": "#A9C3EA"},
    "purple": {**_LIGHT, "bg": "#F3EEFF", "surface": "#FFFFFF", "surface2": "#E8DEFF", "border": "#D6C6F7",
               "accent": "#8A4DFF", "sidebar": "#3B1B7A", "sidebar_text": "#E4D8FF", "sidebar_hover": "#512A9E",
               "sidebar_sel_text": "#3B1B7A", "text": "#26164A", "muted": "#7A68A6", "scroll": "#C6B3EE"},
    "green": {**_LIGHT, "bg": "#EEF8F1", "surface": "#FFFFFF", "surface2": "#DDF0E3", "border": "#C3E2CD",
              "accent": "#1FA65A", "sidebar": "#0F5B35", "sidebar_text": "#D5F3E1", "sidebar_hover": "#17784A",
              "sidebar_sel_text": "#0F5B35", "text": "#12301F", "muted": "#5E8670", "scroll": "#A9D3B8"},
    "teal": {**_LIGHT, "bg": "#ECF9F9", "surface": "#FFFFFF", "surface2": "#D8F1F1", "border": "#BDE5E5",
             "accent": "#0FA3A3", "sidebar": "#0B5D63", "sidebar_text": "#D2F3F3", "sidebar_hover": "#117882",
             "sidebar_sel_text": "#0B5D63", "text": "#0E2F33", "muted": "#58868A", "scroll": "#A3D4D4"},
    "vibrant": {**_DARK, "bg": "#140B2E", "surface": "#201347", "surface2": "#2B1A5E", "border": "#46308A",
                "accent": "#FF4FA3", "on_accent": "#FFFFFF", "sidebar": "#0E0723", "sidebar_text": "#E7D9FF",
                "sidebar_hover": "#2B1A5E", "sidebar_sel_text": "#FFFFFF", "text": "#F6EEFF", "muted": "#A996D9",
                "success": "#3DF2A0", "warn": "#FFC94D", "scroll": "#5B43A8",
                "sidebar_bg_extra": "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2A0F6B, stop:1 #0E0723)"},
}

ACCENT_CHOICES = ["#4F6BED", "#8A4DFF", "#1FA65A", "#0FA3A3", "#FF4FA3", "#FF7A1A", "#E5484D", "#F2B84B"]


def resolve_theme(name: str, system_is_dark: bool = False) -> str:
    if name == "system":
        return "dark" if system_is_dark else "light"
    return name if name in PALETTES else "light"


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(round(v)))) for v in (r, g, b)))


def mix(c1: str, c2: str, t: float) -> str:
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return _rgb_to_hex(*(a[i] + (b[i] - a[i]) * t for i in range(3)))


def readable_on(color: str) -> str:
    r, g, b = _hex_to_rgb(color)
    return "#101326" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#FFFFFF"


def is_valid_hex(c: str) -> bool:
    c = (c or "").strip()
    return len(c) == 7 and c[0] == "#" and all(ch in "0123456789abcdefABCDEF" for ch in c[1:])


def palette_for(theme: str, accent: str = "", system_is_dark: bool = False) -> dict:
    pal = dict(PALETTES[resolve_theme(theme, system_is_dark)])
    if is_valid_hex(accent):
        pal["accent"] = accent.upper()
        pal["on_accent"] = readable_on(accent)
        if theme in ("blue", "purple", "green", "teal"):
            pal["sidebar_sel_text"] = pal["sidebar"]
    pal["accent_hover"] = mix(pal["accent"], "#FFFFFF" if readable_on(pal["accent"]) == "#101326" else "#000000", 0.12)
    pal["accent_soft"] = mix(pal["surface"], pal["accent"], 0.14)
    return pal


def build_qss(pal: dict, font_size: int = 11, font_family: str = "Vazirmatn, 'Segoe UI', Tahoma") -> str:
    sb_bg = pal.get("sidebar_bg_extra") or pal["sidebar"]
    return f"""
* {{ font-family: {font_family}; font-size: {font_size}pt; }}
QMainWindow, QDialog {{ background: {pal['bg']}; color: {pal['text']}; }}
QWidget#page, QStackedWidget {{ background: {pal['bg']}; }}
QLabel {{ color: {pal['text']}; background: transparent; }}
QLabel#muted {{ color: {pal['muted']}; }}
QLabel#h1 {{ font-size: {font_size + 7}pt; font-weight: 700; }}
QLabel#h2 {{ font-size: {font_size + 3}pt; font-weight: 600; }}
QLabel#slogan {{ color: {pal['muted']}; }}
QToolTip {{ background: {pal['surface']}; color: {pal['text']}; border: 1px solid {pal['border']}; padding: 4px; }}

QFrame#sidebar {{ background: {sb_bg}; border: none; }}
QFrame#sidebar QLabel {{ color: {pal['sidebar_text']}; }}
QPushButton#nav {{ background: transparent; color: {pal['sidebar_text']}; border: none; border-radius: 10px;
    padding: 10px 14px; text-align: right; }}
QPushButton#nav:hover {{ background: {pal['sidebar_hover']}; }}
QPushButton#nav:checked {{ background: {pal['accent']}; color: {pal['on_accent']}; font-weight: 600; }}

QFrame#card, QFrame#statCard {{ background: {pal['surface']}; border: 1px solid {pal['border']}; border-radius: 14px; }}
QFrame#statCard:hover, QFrame#card:hover {{ border: 1px solid {pal['accent']}; }}
QFrame#panel {{ background: {pal['surface']}; border: 1px solid {pal['border']}; border-radius: 14px; }}

QPushButton {{ background: {pal['surface2']}; color: {pal['text']}; border: 1px solid {pal['border']};
    border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ border: 1px solid {pal['accent']}; }}
QPushButton:pressed {{ background: {pal['accent_soft']}; }}
QPushButton:disabled {{ color: {pal['muted']}; }}
QPushButton#primary {{ background: {pal['accent']}; color: {pal['on_accent']}; border: none; font-weight: 600;
    padding: 9px 18px; }}
QPushButton#primary:hover {{ background: {pal['accent_hover']}; }}
QPushButton#big {{ background: {pal['accent']}; color: {pal['on_accent']}; border: none; font-weight: 700;
    font-size: {font_size + 3}pt; padding: 14px 26px; border-radius: 14px; }}
QPushButton#big:hover {{ background: {pal['accent_hover']}; }}
QPushButton#danger {{ background: transparent; color: {pal['danger']}; border: 1px solid {pal['danger']}; }}
QPushButton#danger:hover {{ background: {pal['danger']}; color: #FFFFFF; }}
QPushButton#flat {{ background: transparent; border: none; color: {pal['muted']}; padding: 4px 8px; }}
QPushButton#flat:hover {{ color: {pal['accent']}; }}
QPushButton#swatch {{ border-radius: 14px; border: 2px solid {pal['border']}; min-width: 28px; max-width: 28px;
    min-height: 28px; max-height: 28px; padding: 0; }}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit {{ background: {pal['surface']};
    color: {pal['text']}; border: 1px solid {pal['border']}; border-radius: 9px; padding: 7px 10px;
    selection-background-color: {pal['accent']}; selection-color: {pal['on_accent']}; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {pal['accent']}; }}
QLineEdit#search {{ border-radius: 18px; padding: 9px 16px; }}
QComboBox QAbstractItemView {{ background: {pal['surface']}; color: {pal['text']}; border: 1px solid {pal['border']};
    selection-background-color: {pal['accent']}; selection-color: {pal['on_accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}

QListWidget, QTreeWidget, QTableWidget, QListView {{ background: {pal['surface']}; color: {pal['text']};
    border: 1px solid {pal['border']}; border-radius: 12px; outline: none; padding: 4px; }}
QListWidget::item, QTreeWidget::item {{ padding: 8px; border-radius: 8px; margin: 1px 2px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {pal['surface2']}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {pal['accent']}; color: {pal['on_accent']}; }}
QHeaderView::section {{ background: {pal['surface2']}; color: {pal['text']}; border: none; padding: 6px; }}

QCheckBox, QRadioButton {{ color: {pal['text']}; spacing: 8px; }}
QGroupBox {{ border: 1px solid {pal['border']}; border-radius: 12px; margin-top: 14px; padding: 14px 10px 10px 10px;
    background: {pal['surface']}; }}
QGroupBox::title {{ subcontrol-origin: margin; right: 14px; padding: 0 6px; color: {pal['muted']}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {pal['scroll']}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {pal['scroll']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

QTabWidget::pane {{ border: 1px solid {pal['border']}; border-radius: 12px; background: {pal['surface']}; }}
QTabBar::tab {{ background: transparent; color: {pal['muted']}; padding: 8px 16px; border-radius: 8px; margin: 2px; }}
QTabBar::tab:selected {{ background: {pal['accent_soft']}; color: {pal['accent']}; font-weight: 600; }}
QProgressBar {{ border: 1px solid {pal['border']}; border-radius: 8px; background: {pal['surface2']}; text-align: center; }}
QProgressBar::chunk {{ background: {pal['accent']}; border-radius: 7px; }}
QMenu {{ background: {pal['surface']}; color: {pal['text']}; border: 1px solid {pal['border']}; border-radius: 8px;
    padding: 4px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {pal['accent']}; color: {pal['on_accent']}; }}
QLabel#toast {{ background: {pal['text']}; color: {pal['bg']}; border-radius: 16px; padding: 10px 22px; }}
QLabel#chip {{ background: {pal['accent_soft']}; color: {pal['accent']}; border-radius: 10px; padding: 2px 10px; }}
QStatusBar {{ background: {pal['surface']}; color: {pal['muted']}; }}
"""
