"""پنجره‌ی اصلی: نوار کناری، صفحه‌ها، میانبرها، پیام کوتاه، بکاپ خودکار و میانبر سراسری."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME_EN, APP_NAME_FA, APP_SLOGAN, __version__
from ..core.context import AppContext
from ..utils.hotkey import GlobalHotkey
from ..utils.paths import resource_path
from .backup_window import BackupPage
from .categories import CategoriesPage
from .dashboard import DashboardPage
from .prompt_editor import PromptEditorDialog
from .prompt_list import PromptListPage
from .quick_search import QuickSearchDialog
from .settings_window import SettingsPage
from .style import apply_theme
from .templates import TemplatesPage
from .widgets import Toast

NAV = [
    ("dashboard", "🏠", "داشبورد"),
    ("all", "📚", "همه‌ی پرامپت‌ها"),
    ("favorites", "⭐", "علاقه‌مندی‌ها"),
    ("recent", "🕘", "اخیراً استفاده‌شده"),
    ("categories", "🗂️", "دسته‌بندی‌ها و برچسب‌ها"),
    ("templates", "🧩", "قالب‌های آماده"),
    ("archived", "📦", "بایگانی"),
    ("trash", "🗑️", "سطل بازیافت"),
    ("backup", "💾", "بکاپ و انتقال"),
    ("settings", "⚙️", "تنظیمات"),
]
STARTUP_MAP = {"dashboard": "dashboard", "prompts": "all", "favorites": "favorites"}
AUTO_BACKUP_CHECK_MS = 15 * 60 * 1000


def app_icon() -> QIcon:
    p = resource_path("app", "assets", "icon.png")
    return QIcon(str(p)) if p.exists() else QIcon()


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, app: QApplication):
        super().__init__()
        self.ctx = ctx
        self.app = app
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self.current = "dashboard"
        self.setWindowTitle(f"{APP_NAME_FA} — {APP_NAME_EN}")
        self.setWindowIcon(app_icon())
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1360, 840)
        self.setMinimumSize(980, 640)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())      # اولین ویجت در حالت راست‌چین، سمت راست قرار می‌گیرد
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self._build_pages()
        self.toast = Toast(self)

        self.quick = QuickSearchDialog(ctx, None)   # بدون والد؛ تا با کوچک‌بودن پنجره‌ی اصلی هم نمایش داده شود
        self.quick.open_requested.connect(self._open_from_quick)
        self.quick.copied.connect(lambda _t: self._after_data_use())

        self._shortcuts()
        self.hotkey = GlobalHotkey(self._on_global_hotkey)
        self.apply_theme()
        self._restore_geometry()
        self.apply_hotkey()

        self._backup_timer = QTimer(self)
        self._backup_timer.timeout.connect(self._auto_backup_tick)
        self._backup_timer.start(AUTO_BACKUP_CHECK_MS)
        QTimer.singleShot(2000, self._auto_backup_tick)
        try:  # با تغییر تم ویندوز، حالت «خودکار» هم عوض شود (Qt 6.5+)
            app.styleHints().colorSchemeChanged.connect(lambda *_a: self.apply_theme())
        except Exception:
            pass

        start = ctx.settings.get("startup_page") or "dashboard"
        page = ctx.settings.get("last_page") if start == "last" else STARTUP_MAP.get(start, "dashboard")
        self.show_page(page if page in self.pages else "dashboard")

    # ---------------------------------------------------------------- ساخت
    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(232)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(12, 18, 12, 12)
        lay.setSpacing(4)
        logo = QLabel(f"💎 {APP_NAME_FA}")
        logo.setStyleSheet("font-size: 17pt; font-weight: 700;")
        sub = QLabel(APP_NAME_EN)
        sub.setStyleSheet("font-size: 9pt; letter-spacing: 3px; opacity: 0.8;")
        slogan = QLabel(APP_SLOGAN)
        slogan.setWordWrap(True)
        slogan.setStyleSheet("font-size: 8pt;")
        lay.addWidget(logo)
        lay.addWidget(sub)
        lay.addWidget(slogan)
        lay.addSpacing(14)
        group = QButtonGroup(bar)
        group.setExclusive(True)
        for key, icon, text in NAV:
            b = QPushButton(f"{icon}   {text}")
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.show_page(k))
            group.addButton(b)
            lay.addWidget(b)
            self.nav_buttons[key] = b
        lay.addStretch(1)
        quick = QPushButton("🔎  جست‌وجوی سریع  (Ctrl+K)")
        quick.setObjectName("nav")
        quick.setCursor(Qt.PointingHandCursor)
        quick.clicked.connect(lambda _c=False: self.quick.popup())
        lay.addWidget(quick)
        ver = QLabel(f"نسخه‌ی {__version__}")
        ver.setStyleSheet("font-size: 8pt;")
        lay.addWidget(ver)
        return bar

    def _build_pages(self) -> None:
        ctx = self.ctx
        dash = DashboardPage(ctx)
        dash.open_prompt.connect(self.open_editor)
        dash.new_prompt.connect(lambda: self.open_editor(None))
        dash.navigate.connect(self.show_page)
        dash.search_requested.connect(self.search_in_all)
        self._add("dashboard", dash)

        for mode in ("all", "favorites", "recent", "archived", "trash"):
            page = PromptListPage(ctx, mode)
            page.open_prompt.connect(self.open_editor)
            page.new_prompt.connect(lambda: self.open_editor(None))
            page.changed.connect(self.on_changed)
            page.message.connect(self.show_toast)
            self._add(mode, page)

        cats = CategoriesPage(ctx)
        cats.changed.connect(self.on_changed)
        cats.message.connect(self.show_toast)
        cats.open_prompt.connect(self.open_editor)
        cats.new_prompt_in.connect(lambda cid: self.open_editor(None, category_id=cid))
        cats.show_category.connect(self._show_category)
        cats.show_tag.connect(self._show_tag)
        self._add("categories", cats)

        tpl = TemplatesPage(ctx)
        tpl.changed.connect(self.on_changed)
        tpl.message.connect(self.show_toast)
        tpl.create_prompt.connect(lambda title, body, cid: self.open_editor(None, cid, title, body))
        self._add("templates", tpl)

        backup = BackupPage(ctx)
        backup.changed.connect(self.on_changed)
        backup.message.connect(self.show_toast)
        self._add("backup", backup)

        settings = SettingsPage(ctx)
        settings.appearance_changed.connect(self.apply_theme)
        settings.hotkey_changed.connect(self.apply_hotkey)
        settings.changed.connect(self.on_changed)
        settings.message.connect(self.show_toast)
        self._add("settings", settings)

    def _add(self, key: str, page: QWidget) -> None:
        self.pages[key] = page
        self.stack.addWidget(page)

    def _shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.open_editor(None))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.focus_search)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.quick.popup)

    # ---------------------------------------------------------------- ناوبری
    def show_page(self, key: str) -> None:
        if key not in self.pages:
            return
        self.current = key
        if key in self.nav_buttons:
            self.nav_buttons[key].setChecked(True)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "refresh"):
            page.refresh()
        self.ctx.settings.set("last_page", key)
        self._update_status()

    def refresh_current(self) -> None:
        page = self.pages.get(self.current)
        if page is not None and hasattr(page, "refresh"):
            page.refresh()
        self._update_status()

    def focus_search(self) -> None:
        page = self.pages.get(self.current)
        if not hasattr(page, "focus_search"):
            self.show_page("all")
            page = self.pages["all"]
        page.focus_search()

    def search_in_all(self, text: str) -> None:
        self.show_page("all")
        page = self.pages["all"]
        page.reset_filters()
        page.set_query(text)

    def _show_category(self, category_id: int) -> None:
        self.show_page("all")
        page = self.pages["all"]
        page.reset_filters()
        page.set_category(category_id)

    def _show_tag(self, name: str) -> None:
        self.show_page("all")
        page = self.pages["all"]
        page.reset_filters()
        page.set_tag(name)

    # ---------------------------------------------------------------- داده
    def open_editor(self, prompt_id: int | None = None, category_id: int | None = None,
                    title: str = "", body: str = "") -> None:
        dlg = PromptEditorDialog(self.ctx, prompt_id, self, category_id=category_id,
                                 initial_title=title, initial_body=body)
        dlg.exec()
        self.refresh_current()

    def _open_from_quick(self, prompt_id: int) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.open_editor(prompt_id)

    def on_changed(self) -> None:
        self.ctx.settings.set("data_changed_since_backup", True)
        self.refresh_current()

    def _after_data_use(self) -> None:
        self.refresh_current()

    def show_toast(self, text: str) -> None:
        self.toast.show_message(text)

    def _update_status(self) -> None:
        try:
            st = self.ctx.prompts.stats()
            self.statusBar().showMessage(
                f"{st['total']} پرامپت  •  {st['categories']} دسته‌بندی  •  {st['tags']} برچسب  •  "
                f"محل داده‌ها: {self.ctx.data_dir}")
        except Exception:
            pass

    # ---------------------------------------------------------------- ظاهر / میانبر سراسری
    def apply_theme(self) -> None:
        apply_theme(self.app, self.ctx.settings)

    def apply_hotkey(self) -> None:
        text = self.ctx.settings.get("global_search_hotkey") or ""
        settings_page = self.pages.get("settings")
        if not text:
            self.hotkey.unregister()
            return
        ok = self.hotkey.register(text)
        if hasattr(settings_page, "set_hotkey_status") and GlobalHotkey.supported():
            settings_page.set_hotkey_status(ok, text)

    def _on_global_hotkey(self) -> None:
        self.quick.popup()

    # ---------------------------------------------------------------- بکاپ خودکار
    def _auto_backup_tick(self) -> None:
        try:
            path = self.ctx.backups.run_if_due()
        except Exception as e:  # noqa: BLE001
            self.show_toast(f"بکاپ خودکار انجام نشد: {e}")
            return
        if path:
            self.show_toast("بکاپ خودکار ساخته شد")

    # ---------------------------------------------------------------- پنجره
    def _restore_geometry(self) -> None:
        g = self.ctx.settings.get("window_geometry")
        if g:
            try:
                self.restoreGeometry(QByteArray.fromBase64(g.encode("ascii")))
            except Exception:
                pass

    def closeEvent(self, ev) -> None:  # noqa: N802
        try:
            self.ctx.settings.set("window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        except Exception:
            pass
        try:
            self.ctx.backups.run_on_exit()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "بکاپ هنگام خروج", f"ساخت بکاپ خودکار هنگام خروج انجام نشد:\n{e}")
        self.hotkey.unregister()
        self.quick.close()
        ev.accept()
