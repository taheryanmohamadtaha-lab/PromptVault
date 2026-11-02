"""صفحه‌ی بکاپ و انتقال اطلاعات: ساخت بکاپ، خروجی‌ها، بازیابی با پیش‌نمایش، فهرست بکاپ‌ها."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.context import AppContext
from ..core.export_manager import ALL_PARTS
from ..core.import_manager import PVaultError, load_package
from .dialogs import ImportPreviewDialog, confirm, error, info, select_combo_data

PART_NAMES = {
    "categories": "دسته‌بندی‌ها", "tags": "برچسب‌ها", "prompts": "پرامپت‌ها", "versions": "تاریخچه‌ی نسخه‌ها",
    "templates": "قالب‌های آماده", "attachments": "اطلاعات پیوست‌ها", "settings": "تنظیمات شخصی",
}
SCHEDULES = [("daily", "روزانه"), ("weekly", "هفتگی"), ("on_exit", "هنگام خروج از برنامه"),
             ("on_exit_if_changed", "هنگام بستن برنامه، فقط اگر اطلاعات تغییر کرده باشد")]


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def run_restore(ctx: AppContext, parent: QWidget, path: str | Path) -> bool:
    """مراحل کامل بازیابی: خواندن و اعتبارسنجی → پیش‌نمایش → تصمیم کاربر → بکاپ ایمنی → اعمال.
    True یعنی اطلاعات تغییر کرد."""
    try:
        pkg = load_package(path)
    except PVaultError as e:
        error(parent, "فایل بکاپ معتبر نیست", str(e))
        return False
    except Exception as e:  # noqa: BLE001 - هر خطای پیش‌بینی‌نشده برای کاربر قابل فهم باشد
        error(parent, "خواندن فایل ممکن نشد", f"{type(e).__name__}: {e}")
        return False
    dlg = ImportPreviewDialog(ctx, pkg, parent)
    if not dlg.exec():
        return False
    try:
        res = ctx.importer.apply(pkg, **dlg.options())
    except PVaultError as e:
        error(parent, "بازیابی انجام نشد", f"{e}\n\nاطلاعات فعلی شما دست‌نخورده باقی ماند.")
        return False
    except Exception as e:  # noqa: BLE001
        error(parent, "بازیابی انجام نشد",
              f"خطای غیرمنتظره: {type(e).__name__}: {e}\n\nاطلاعات فعلی شما دست‌نخورده باقی ماند.")
        return False
    lines = [f"پرامپت جدید: {res.added}", f"جایگزین‌شده: {res.replaced}", f"رد‌شده: {res.skipped}",
             f"هر دو نگه‌داشته‌شده: {res.duplicated}", f"قالب‌های جدید: {res.templates_added}",
             f"دسته‌بندی‌های جدید: {res.categories_added}", f"پیوست‌های وارد‌شده: {res.attachments_added}"]
    if res.attachments_missing:
        lines.append(f"پیوست‌های ناموجود در فایل: {res.attachments_missing}")
    if res.safety_backup:
        lines.append(f"\nقبل از بازیابی یک بکاپ ایمنی ساخته شد:\n{res.safety_backup}")
    info(parent, "بازیابی با موفقیت انجام شد", "\n".join(lines))
    return True


class AutoBackupGroup(QGroupBox):
    """تنظیمات بکاپ خودکار؛ هم در صفحه‌ی بکاپ و هم در تنظیمات استفاده می‌شود."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__("بکاپ خودکار", parent)
        self.ctx = ctx
        self._loading = True
        grid = QGridLayout(self)
        self.enabled = QCheckBox("بکاپ خودکار فعال باشد")
        self.schedule = QComboBox()
        for key, text in SCHEDULES:
            self.schedule.addItem(text, key)
        self.keep = QSpinBox()
        self.keep.setRange(1, 200)
        self.keep.setSuffix(" نسخه")
        self.dir_label = QLabel("")
        self.dir_label.setWordWrap(True)
        self.dir_btn = QPushButton("تغییر مسیر بکاپ‌ها …")
        self.dir_reset = QPushButton("مسیر پیش‌فرض")
        self.open_btn = QPushButton("باز کردن پوشه")
        self.rotate_btn = QPushButton("حذف بکاپ‌های قدیمی‌تر از تعداد مجاز")
        grid.addWidget(self.enabled, 0, 0, 1, 3)
        grid.addWidget(QLabel("زمان‌بندی:"), 1, 0)
        grid.addWidget(self.schedule, 1, 1, 1, 2)
        grid.addWidget(QLabel("تعداد نسخه‌های نگهداری‌شده:"), 2, 0)
        grid.addWidget(self.keep, 2, 1, 1, 2)
        grid.addWidget(QLabel("مسیر ذخیره:"), 3, 0)
        grid.addWidget(self.dir_label, 3, 1, 1, 2)
        grid.addWidget(self.dir_btn, 4, 0)
        grid.addWidget(self.dir_reset, 4, 1)
        grid.addWidget(self.open_btn, 4, 2)
        grid.addWidget(self.rotate_btn, 5, 0, 1, 3)
        self.enabled.toggled.connect(lambda v: self._save("backup_auto_enabled", v))
        self.schedule.currentIndexChanged.connect(lambda _i: self._save("backup_schedule", self.schedule.currentData()))
        self.keep.valueChanged.connect(lambda v: self._save("backup_keep", v))
        self.dir_btn.clicked.connect(self._choose_dir)
        self.dir_reset.clicked.connect(self._reset_dir)
        self.open_btn.clicked.connect(lambda: open_folder(self.ctx.backups.backup_dir()))
        self.rotate_btn.clicked.connect(self._rotate)
        self.load()

    def load(self) -> None:
        s = self.ctx.settings
        self._loading = True
        self.enabled.setChecked(bool(s.get("backup_auto_enabled")))
        select_combo_data(self.schedule, s.get("backup_schedule"))
        self.keep.setValue(int(s.get("backup_keep") or 10))
        self.dir_label.setText(str(self.ctx.backups.backup_dir()))
        self._loading = False

    def _save(self, key: str, value) -> None:
        if not self._loading:
            self.ctx.settings.set(key, value)

    def _choose_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی ذخیره‌ی بکاپ‌ها", str(self.ctx.backups.backup_dir()))
        if folder:
            self.ctx.settings.set("backup_dir", folder)
            self.load()

    def _reset_dir(self) -> None:
        self.ctx.settings.set("backup_dir", "")
        self.load()

    def _rotate(self) -> None:
        removed = self.ctx.backups.rotate()
        info(self, "پاک‌سازی بکاپ‌ها",
             f"{len(removed)} بکاپ قدیمی حذف شد." if removed else "بکاپ قدیمی‌ای برای حذف وجود نداشت.")


class BackupPage(QWidget):
    changed = Signal()
    message = Signal(str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
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
        t = QLabel("بکاپ و انتقال اطلاعات")
        t.setObjectName("h1")
        root.addWidget(t)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        # ---- ساخت بکاپ
        g1 = QGroupBox("ساخت بکاپ کامل (.pvault)")
        l1 = QVBoxLayout(g1)
        l1.addWidget(QLabel("همه‌ی پرامپت‌ها، دسته‌بندی‌ها، برچسب‌ها، نسخه‌ها، قالب‌ها، پیوست‌ها و تنظیمات در یک فایل قابل انتقال."))
        r1 = QHBoxLayout()
        b_default = QPushButton("💾 ساخت بکاپ (مسیر پیش‌فرض)")
        b_default.setObjectName("primary")
        b_custom = QPushButton("ذخیره‌ی بکاپ در مسیر دلخواه …")
        b_default.clicked.connect(lambda: self._backup(None))
        b_custom.clicked.connect(self._backup_custom)
        r1.addWidget(b_default)
        r1.addWidget(b_custom)
        r1.addStretch(1)
        l1.addLayout(r1)
        root.addWidget(g1)

        # ---- بازیابی
        g2 = QGroupBox("بازیابی / انتقال به این کامپیوتر")
        l2 = QVBoxLayout(g2)
        l2.addWidget(QLabel("فایل .pvault (یا JSON) را انتخاب کنید. قبل از هر تغییر پیش‌نمایش می‌بینید و از وضعیت فعلی یک بکاپ ایمنی گرفته می‌شود."))
        b_restore = QPushButton("📂 انتخاب فایل و بازیابی …")
        b_restore.clicked.connect(self._restore_from_file)
        l2.addWidget(b_restore, 0, Qt.AlignRight)
        root.addWidget(g2)

        # ---- خروجی‌ها
        g3 = QGroupBox("خروجی گرفتن (برای استفاده در برنامه‌های دیگر)")
        l3 = QVBoxLayout(g3)
        l3.addWidget(QLabel("موارد خروجی JSON را انتخاب کنید:"))
        parts = QHBoxLayout()
        self.part_cbs: dict[str, QCheckBox] = {}
        for key in ALL_PARTS:
            cb = QCheckBox(PART_NAMES[key])
            cb.setChecked(True)
            self.part_cbs[key] = cb
            parts.addWidget(cb)
        parts.addStretch(1)
        l3.addLayout(parts)
        r3 = QHBoxLayout()
        for text, fn in (("JSON", self._export_json), ("CSV (فهرست پرامپت‌ها)", self._export_csv),
                         ("Markdown", self._export_md), ("TXT", self._export_txt)):
            b = QPushButton("⬇ " + text)
            b.clicked.connect(fn)
            r3.addWidget(b)
        r3.addStretch(1)
        l3.addLayout(r3)
        root.addWidget(g3)

        # ---- بکاپ خودکار
        self.auto = AutoBackupGroup(ctx)
        root.addWidget(self.auto)

        # ---- فهرست بکاپ‌ها
        g4 = QGroupBox("بکاپ‌های موجود در پوشه‌ی بکاپ")
        l4 = QVBoxLayout(g4)
        self.list = QListWidget()
        self.list.setMinimumHeight(150)
        l4.addWidget(self.list)
        r4 = QHBoxLayout()
        self.b_restore_sel = QPushButton("بازیابی از این بکاپ")
        self.b_verify = QPushButton("بررسی سلامت")
        self.b_delete = QPushButton("حذف")
        self.b_delete.setObjectName("danger")
        self.b_open = QPushButton("باز کردن پوشه")
        self.b_restore_sel.clicked.connect(self._restore_selected)
        self.b_verify.clicked.connect(self._verify_selected)
        self.b_delete.clicked.connect(self._delete_selected)
        self.b_open.clicked.connect(lambda: open_folder(self.ctx.backups.backup_dir()))
        for b in (self.b_restore_sel, self.b_verify, self.b_open):
            r4.addWidget(b)
        r4.addStretch(1)
        r4.addWidget(self.b_delete)
        l4.addLayout(r4)
        root.addWidget(g4)
        root.addStretch(1)
        self.list.itemSelectionChanged.connect(self._sel_changed)

    # ---------------------------------------------------------------- نمایش
    def refresh(self) -> None:
        self.auto.load()
        changed = bool(self.ctx.settings.get("data_changed_since_backup"))
        self.status.setText(
            "⚠️ از آخرین بکاپ تا الان اطلاعات تغییر کرده است. بهتر است بکاپ تازه بگیرید."
            if changed else "✅ از آخرین بکاپ تغییری در اطلاعات ثبت نشده است.")
        self.list.clear()
        for b in self.ctx.backups.list_backups():
            kind = "ایمنی (پیش از بازیابی)" if b.is_safety else "بکاپ"
            it = QListWidgetItem(f"{b.path.name}   —   {b.modified:%Y-%m-%d %H:%M}   —   {b.size / 1024:.0f} KB")
            it.setData(Qt.UserRole, str(b.path))
            it.setToolTip(kind)
            self.list.addItem(it)
        # بکاپ‌های ایمنی در پوشه‌ی جداگانه‌اند؛ آن‌ها هم نشان داده شوند
        for b in self.ctx.backups.list_backups(self.ctx.backups.safety_dir()):
            it = QListWidgetItem(f"🛡️ {b.path.name}   —   {b.modified:%Y-%m-%d %H:%M}   —   {b.size / 1024:.0f} KB")
            it.setData(Qt.UserRole, str(b.path))
            it.setToolTip("بکاپ ایمنی که قبل از یک بازیابی ساخته شد")
            self.list.addItem(it)
        self._sel_changed()

    def _sel_changed(self) -> None:
        has = bool(self.list.selectedItems())
        for b in (self.b_restore_sel, self.b_verify, self.b_delete):
            b.setEnabled(has)

    def _selected_path(self) -> str | None:
        items = self.list.selectedItems()
        return items[0].data(Qt.UserRole) if items else None

    # ---------------------------------------------------------------- بکاپ
    def _backup(self, folder: str | None) -> None:
        try:
            path = self.ctx.backups.create_backup(folder)
        except Exception as e:  # noqa: BLE001
            error(self, "ساخت بکاپ ناموفق بود", f"{e}")
            return
        self.message.emit("بکاپ با موفقیت ساخته شد")
        info(self, "بکاپ ساخته شد", f"فایل بکاپ سالم است و اینجا ذخیره شد:\n{path}")
        self.refresh()

    def _backup_custom(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "پوشه‌ی ذخیره‌ی بکاپ", str(Path.home()))
        if folder:
            self._backup(folder)

    # ---------------------------------------------------------------- بازیابی
    def _restore_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب فایل بکاپ", str(self.ctx.backups.backup_dir()),
            "فایل بکاپ گنجینه پرامپت (*.pvault *.json);;همه‌ی فایل‌ها (*)")
        if path:
            self._restore(path)

    def _restore_selected(self) -> None:
        p = self._selected_path()
        if p:
            self._restore(p)

    def _restore(self, path: str) -> None:
        if run_restore(self.ctx, self, path):
            self.changed.emit()
            self.refresh()

    def _verify_selected(self) -> None:
        p = self._selected_path()
        if not p:
            return
        try:
            m = self.ctx.backups.verify(p)
        except PVaultError as e:
            error(self, "بکاپ مشکل دارد", str(e))
            return
        c = m.get("counts", {})
        info(self, "بکاپ سالم است",
             f"پرامپت‌ها: {c.get('prompts', '؟')}\nدسته‌بندی‌ها: {c.get('categories', '؟')}\n"
             f"قالب‌ها: {c.get('templates', '؟')}\nساخته‌شده: {str(m.get('created_at', '؟')).replace('T', ' ')}")

    def _delete_selected(self) -> None:
        p = self._selected_path()
        if p and confirm(self, "حذف بکاپ", f"این فایل بکاپ برای همیشه حذف شود؟\n{Path(p).name}", "حذف", danger=True):
            self.ctx.backups.delete_backup(p)
            self.refresh()

    # ---------------------------------------------------------------- خروجی‌ها
    def _export(self, caption: str, default_name: str, filt: str, writer) -> None:
        start = str(Path.home() / default_name)
        path, _ = QFileDialog.getSaveFileName(self, caption, start, filt)
        if not path:
            return
        try:
            out = writer(path)
        except Exception as e:  # noqa: BLE001
            error(self, "خروجی گرفتن ناموفق بود", str(e))
            return
        self.message.emit("خروجی ذخیره شد")
        info(self, "خروجی ذخیره شد", str(out))

    @staticmethod
    def _stamp() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M")

    def _export_json(self) -> None:
        parts = [k for k, cb in self.part_cbs.items() if cb.isChecked()]
        if not parts:
            error(self, "موردی انتخاب نشده", "حداقل یک مورد را برای خروجی انتخاب کنید.")
            return
        self._export("ذخیره‌ی JSON", f"PromptVault_{self._stamp()}.json", "JSON (*.json)",
                     lambda p: self.ctx.exporter.export_json(p, parts))

    def _export_csv(self) -> None:
        self._export("ذخیره‌ی CSV", f"PromptVault_{self._stamp()}.csv", "CSV (*.csv)",
                     self.ctx.exporter.export_csv)

    def _export_md(self) -> None:
        self._export("ذخیره‌ی Markdown", f"PromptVault_{self._stamp()}.md", "Markdown (*.md)",
                     self.ctx.exporter.export_markdown)

    def _export_txt(self) -> None:
        self._export("ذخیره‌ی TXT", f"PromptVault_{self._stamp()}.txt", "متن (*.txt)",
                     self.ctx.exporter.export_txt)
