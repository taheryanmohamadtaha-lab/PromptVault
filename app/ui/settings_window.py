"""صفحه‌ی تنظیمات: ظاهر، ویرایشگر، شروع برنامه، محل ذخیره‌ی اطلاعات، بکاپ خودکار، میانبر سراسری و درباره."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QKeySequenceEdit,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import APP_NAME_EN, APP_NAME_FA, __version__
from ..core.context import AppContext
from ..themes.themes import ACCENT_CHOICES, THEME_NAMES
from ..utils.hotkey import GlobalHotkey, parse_hotkey
from ..utils.paths import default_data_dir, set_data_dir
from .backup_window import AutoBackupGroup, open_folder
from .dialogs import confirm, error, info, select_combo_data

STARTUP_PAGES = [("dashboard", "داشبورد"), ("prompts", "همه‌ی پرامپت‌ها"), ("favorites", "علاقه‌مندی‌ها"),
                 ("last", "همان صفحه‌ای که آخرین بار باز بود")]


class SettingsPage(QWidget):
    appearance_changed = Signal()      # تم / رنگ / اندازه‌ی فونت
    hotkey_changed = Signal()
    changed = Signal()
    message = Signal(str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self._loading = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("page")
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(26, 20, 26, 20)
        root.setSpacing(12)
        t = QLabel("تنظیمات")
        t.setObjectName("h1")
        root.addWidget(t)

        # ---- ظاهر
        g = QGroupBox("ظاهر برنامه")
        f = QFormLayout(g)
        self.theme = QComboBox()
        for key, name in THEME_NAMES.items():
            self.theme.addItem(name, key)
        self.theme.currentIndexChanged.connect(lambda _i: self._set("theme", self.theme.currentData(), True))
        f.addRow("تم:", self.theme)
        sw = QHBoxLayout()
        for color in ACCENT_CHOICES:
            b = QPushButton()
            b.setObjectName("swatch")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(color)
            b.setStyleSheet(f"background: {color};")
            b.clicked.connect(lambda _c=False, c=color: self._set("accent_color", c, True))
            sw.addWidget(b)
        custom = QPushButton("رنگ دلخواه …")
        custom.clicked.connect(self._custom_accent)
        reset = QPushButton("رنگ پیش‌فرض تم")
        reset.clicked.connect(lambda: self._set("accent_color", "", True))
        sw.addWidget(custom)
        sw.addWidget(reset)
        sw.addStretch(1)
        f.addRow("رنگ تأکیدی:", sw)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 20)
        self.font_size.setSuffix(" pt")
        self.font_size.valueChanged.connect(lambda v: self._set("font_size", v, True))
        f.addRow("اندازه‌ی فونت برنامه:", self.font_size)
        self.preview = QCheckBox("در فهرست پرامپت‌ها خلاصه‌ی متن هم نمایش داده شود")
        self.preview.toggled.connect(lambda v: self._set("list_show_preview", v))
        f.addRow("نمایش:", self.preview)
        root.addWidget(g)

        # ---- ویرایشگر
        g = QGroupBox("ویرایشگر پرامپت")
        f = QFormLayout(g)
        self.ed_size = QSpinBox()
        self.ed_size.setRange(8, 32)
        self.ed_size.setSuffix(" pt")
        self.ed_size.valueChanged.connect(lambda v: self._set("editor_font_size", v))
        self.ed_wrap = QCheckBox("شکستن خودکار خط‌های بلند")
        self.ed_wrap.toggled.connect(lambda v: self._set("editor_wrap", v))
        self.ed_auto = QCheckBox("ذخیره‌ی خودکار هنگام نوشتن")
        self.ed_auto.toggled.connect(lambda v: self._set("editor_autosave", v))
        f.addRow("اندازه‌ی متن:", self.ed_size)
        f.addRow("", self.ed_wrap)
        f.addRow("", self.ed_auto)
        root.addWidget(g)

        # ---- شروع
        g = QGroupBox("هنگام شروع برنامه")
        f = QFormLayout(g)
        self.startup = QComboBox()
        for key, name in STARTUP_PAGES:
            self.startup.addItem(name, key)
        self.startup.currentIndexChanged.connect(lambda _i: self._set("startup_page", self.startup.currentData()))
        f.addRow("صفحه‌ی آغازین:", self.startup)
        root.addWidget(g)

        # ---- محل داده
        g = QGroupBox("محل ذخیره‌ی اطلاعات")
        v = QVBoxLayout(g)
        self.data_label = QLabel("")
        self.data_label.setWordWrap(True)
        self.data_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.data_label)
        r = QHBoxLayout()
        b1 = QPushButton("تغییر محل ذخیره‌ی اطلاعات …")
        b2 = QPushButton("بازگشت به محل پیش‌فرض")
        b3 = QPushButton("باز کردن پوشه")
        b1.clicked.connect(self._change_data_dir)
        b2.clicked.connect(self._reset_data_dir)
        b3.clicked.connect(lambda: open_folder(self.ctx.data_dir))
        for b in (b1, b2, b3):
            r.addWidget(b)
        r.addStretch(1)
        v.addLayout(r)
        root.addWidget(g)

        # ---- بکاپ خودکار
        self.auto = AutoBackupGroup(ctx)
        root.addWidget(self.auto)

        # ---- دسته‌بندی‌های پیش‌فرض
        g = QGroupBox("دسته‌بندی‌های پیش‌فرض")
        v = QVBoxLayout(g)
        v.addWidget(QLabel("اگر دسته‌بندی‌های اولیه (مثل «اندیکاتورهای MT5») را حذف کرده‌اید، می‌توانید دوباره اضافه‌شان کنید. "
                           "دسته‌بندی‌های موجود دست‌نخورده می‌مانند."))
        b = QPushButton("بازگرداندن دسته‌بندی‌های پیش‌فرضِ حذف‌شده")
        b.clicked.connect(self._restore_defaults)
        v.addWidget(b, 0, Qt.AlignRight)
        root.addWidget(g)

        # ---- میانبر سراسری
        g = QGroupBox("جست‌وجوی سریع سراسری")
        v = QVBoxLayout(g)
        v.addWidget(QLabel("با این میانبر، پنجره‌ی جست‌وجوی سریع از هر جای ویندوز باز می‌شود (حتی وقتی برنامه کوچک شده است). "
                           "داخل برنامه همیشه Ctrl+K هم کار می‌کند."))
        r = QHBoxLayout()
        self.hotkey = QKeySequenceEdit()
        self.hotkey_apply = QPushButton("اعمال میانبر")
        self.hotkey_apply.clicked.connect(self._apply_hotkey)
        self.hotkey_status = QLabel("")
        self.hotkey_status.setObjectName("muted")
        r.addWidget(self.hotkey, 1)
        r.addWidget(self.hotkey_apply)
        v.addLayout(r)
        v.addWidget(self.hotkey_status)
        if not GlobalHotkey.supported():
            self.hotkey_apply.setEnabled(False)
            self.hotkey_status.setText("میانبر سراسری فقط در ویندوز فعال است.")
        root.addWidget(g)

        # ---- درباره
        g = QGroupBox("درباره‌ی برنامه")
        v = QVBoxLayout(g)
        v.addWidget(QLabel(f"<b>{APP_NAME_FA} ({APP_NAME_EN})</b> — نسخه‌ی {__version__}"))
        v.addWidget(QLabel("سازنده: محمدطاها طاهریان"))
        v.addWidget(QLabel("تمام اطلاعات فقط روی همین کامپیوتر می‌ماند و برنامه هیچ داده‌ای به اینترنت نمی‌فرستد."))
        v.addWidget(QLabel("آدرس صفحه‌ی انتشار نسخه‌ها (GitHub Releases):"))
        self.update_url = QLineEdit()
        self.update_url.setPlaceholderText("https://github.com/نام-کاربری/PromptVault/releases")
        self.update_url.editingFinished.connect(self._save_update_url)
        v.addWidget(self.update_url)
        up = QPushButton("بررسی نسخه‌ی جدید (باز شدن صفحه‌ی انتشار در مرورگر)")
        up.clicked.connect(self._open_updates)
        v.addWidget(up, 0, Qt.AlignRight)
        root.addWidget(g)
        root.addStretch(1)
        self._loading = False

    # ---------------------------------------------------------------- بارگذاری/ذخیره
    def refresh(self) -> None:
        s = self.ctx.settings
        self._loading = True
        select_combo_data(self.theme, s.get("theme"))
        self.font_size.setValue(int(s.get("font_size") or 11))
        self.preview.setChecked(bool(s.get("list_show_preview")))
        self.ed_size.setValue(int(s.get("editor_font_size") or 12))
        self.ed_wrap.setChecked(bool(s.get("editor_wrap")))
        self.ed_auto.setChecked(bool(s.get("editor_autosave")))
        select_combo_data(self.startup, s.get("startup_page"))
        self.data_label.setText(str(self.ctx.data_dir))
        self.hotkey.setKeySequence(QKeySequence(s.get("global_search_hotkey") or ""))
        self.auto.load()
        self.update_url.setText(s.get("update_url") or "")
        self._loading = False

    def _save_update_url(self) -> None:
        url = self.update_url.text().strip()
        if url and not url.startswith("https://"):
            error(self, "آدرس نامعتبر", "آدرس باید با https:// شروع شود.")
            return
        self._set("update_url", url)

    def _set(self, key: str, value, appearance: bool = False) -> None:
        if self._loading:
            return
        self.ctx.settings.set(key, value)
        if appearance:
            self.appearance_changed.emit()

    def _custom_accent(self) -> None:
        cur = self.ctx.settings.get("accent_color") or "#4F6BED"
        c = QColorDialog.getColor(QColor(cur), self, "رنگ تأکیدی")
        if c.isValid():
            self._set("accent_color", c.name().upper(), True)

    # ---------------------------------------------------------------- محل داده
    def _change_data_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی جدید برای ذخیره‌ی اطلاعات", str(Path.home()))
        if not folder:
            return
        target = Path(folder)
        if target.resolve() == self.ctx.data_dir.resolve():
            info(self, "بدون تغییر", "این همان محل فعلی است.")
            return
        if not (target / "promptvault.db").exists():
            target = target / "PromptVault_Data"
        try:
            if (target / "promptvault.db").exists():
                if not confirm(self, "اطلاعات موجود در پوشه",
                               f"در این پوشه از قبل اطلاعات گنجینه پرامپت وجود دارد:\n{target}\n\n"
                               "برنامه از این اطلاعات استفاده کند؟ (اطلاعات فعلی کپی یا حذف نمی‌شود و همان‌جا می‌ماند.)",
                               "بله، از همین پوشه استفاده شود"):
                    return
            else:
                if not confirm(self, "انتقال اطلاعات",
                               f"اطلاعات فعلی شما به این مسیر کپی می‌شود:\n{target}\n\n"
                               "نسخه‌ی قبلی پاک نمی‌شود. ادامه می‌دهید؟", "بله، کپی شود"):
                    return
                target.mkdir(parents=True, exist_ok=True)
                self.ctx.db.snapshot_to(target / "promptvault.db")
                if self.ctx.attachments_dir.is_dir():
                    shutil.copytree(self.ctx.attachments_dir, target / "attachments", dirs_exist_ok=True)
            set_data_dir(target)
        except (OSError, shutil.Error) as e:
            error(self, "تغییر محل ممکن نشد", f"{e}")
            return
        info(self, "محل جدید ثبت شد", f"برنامه را ببندید و دوباره باز کنید تا از این مسیر استفاده کند:\n{target}")

    def _reset_data_dir(self) -> None:
        if confirm(self, "بازگشت به محل پیش‌فرض",
                   f"در اجرای بعدی از محل پیش‌فرض استفاده می‌شود:\n{default_data_dir()}\n"
                   "(اطلاعات محل فعلی حذف نمی‌شود.)", "بله"):
            set_data_dir(None)
            info(self, "ثبت شد", "برنامه را ببندید و دوباره باز کنید.")

    # ---------------------------------------------------------------- سایر
    def _restore_defaults(self) -> None:
        n = self.ctx.categories.restore_missing_defaults()
        self.message.emit(f"{n} دسته‌بندی پیش‌فرض بازگردانده شد" if n else "همه‌ی دسته‌بندی‌های پیش‌فرض موجود است")
        if n:
            self.changed.emit()

    def _apply_hotkey(self) -> None:
        text = self.hotkey.keySequence().toString()
        if not text:
            self.ctx.settings.set("global_search_hotkey", "")
            self.hotkey_status.setText("میانبر سراسری غیرفعال شد.")
        elif parse_hotkey(text) is None:
            self.hotkey_status.setText("این ترکیب معتبر نیست. حداقل یکی از Ctrl/Alt/Win را همراه یک حرف، عدد، F1..F12 یا Space بگیرید.")
            return
        else:
            self.ctx.settings.set("global_search_hotkey", text)
            self.hotkey_status.setText("در حال اعمال …")
        self.hotkey_changed.emit()

    def set_hotkey_status(self, ok: bool, text: str) -> None:
        self.hotkey_status.setText(("✅ فعال شد: " if ok else "⚠️ ثبت نشد (شاید برنامه‌ی دیگری از آن استفاده می‌کند): ") + text)

    def _open_updates(self) -> None:
        url = self.ctx.settings.get("update_url") or ""
        if url.startswith("https://"):
            QDesktopServices.openUrl(QUrl(url))
        else:
            info(self, "آدرس تنظیم نشده",
                 "ابتدا در کادر بالا آدرس صفحه‌ی انتشار را بنویسید، مثلاً:\n"
                 "https://github.com/نام-کاربری/PromptVault/releases")
