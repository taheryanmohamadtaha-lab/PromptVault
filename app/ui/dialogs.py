"""پنجره‌های گفتگوی مشترک: تأیید، انتقال، تاریخچه‌ی نسخه، مقایسه، پیش‌نمایش بازیابی، پر کردن قالب."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from ..core import import_manager as im
from ..core.context import AppContext
from ..services.template_service import extract_variables, render
from ..services.version_service import VersionService


# ---------------------------------------------------------------- کمکی‌ها
def confirm(parent: QWidget, title: str, text: str, yes: str = "بله، انجام شود", danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes_btn = box.addButton(yes, QMessageBox.AcceptRole)
    box.addButton("انصراف", QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes_btn


def info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def error(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def fill_category_combo(combo: QComboBox, ctx: AppContext, include_none: str = "بدون دسته‌بندی",
                        include_all: str | None = None) -> None:
    """کمبوباکس دسته‌بندی به‌صورت درختی (با تورفتگی). userData = id دسته (یا None)."""
    combo.clear()
    if include_all:
        combo.addItem(include_all, "__all__")
    if include_none:
        combo.addItem(include_none, None)

    def walk(nodes, depth):
        for c in nodes:
            combo.addItem(f"{'    ' * depth}{c.icon} {c.name}", c.id)
            walk(c.children, depth + 1)

    walk(ctx.categories.tree(), 0)


def select_combo_data(combo: QComboBox, data) -> None:
    for i in range(combo.count()):
        if combo.itemData(i) == data:
            combo.setCurrentIndex(i)
            return


def copy_to_clipboard(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


# ---------------------------------------------------------------- انتقال به دسته
class MoveDialog(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None, title: str = "انتقال به دسته‌بندی"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("دسته‌بندی مقصد را انتخاب کنید:"))
        self.combo = QComboBox()
        fill_category_combo(self.combo, ctx)
        lay.addWidget(self.combo)
        bb = QDialogButtonBox()
        ok = bb.addButton("انتقال", QDialogButtonBox.AcceptRole)
        ok.setObjectName("primary")
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def category_id(self) -> int | None:
        return self.combo.currentData()


# ---------------------------------------------------------------- تاریخچه‌ی نسخه‌ها
class VersionHistoryDialog(QDialog):
    def __init__(self, ctx: AppContext, prompt_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.prompt_id = prompt_id
        self.restored = False
        self.setWindowTitle("تاریخچه‌ی نسخه‌ها")
        self.resize(940, 560)
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("نسخه‌ها (جدیدترین بالاست)"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        ll.addWidget(self.list, 1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItems(["نمایش متن این نسخه", "مقایسه با نسخه‌ی فعلی", "مقایسه با نسخه‌ی قبل از آن"])
        self.mode.currentIndexChanged.connect(lambda _=0: self._show(self.list.currentRow()))
        rl.addWidget(self.mode)
        self.view = QTextBrowser()
        rl.addWidget(self.view, 1)
        note_row = QHBoxLayout()
        self.note = QLineEdit()
        self.note.setPlaceholderText("توضیح این نسخه (مثلاً: «کوتاه‌تر شد»)")
        save_note = QPushButton("ذخیره‌ی توضیح")
        save_note.clicked.connect(self._save_note)
        note_row.addWidget(self.note, 1)
        note_row.addWidget(save_note)
        rl.addLayout(note_row)
        split.addWidget(right)
        split.setSizes([300, 640])

        btns = QHBoxLayout()
        self.restore_btn = QPushButton("بازیابی این نسخه")
        self.restore_btn.setObjectName("primary")
        self.restore_btn.clicked.connect(self._restore)
        close = QPushButton("بستن")
        close.clicked.connect(self.accept)
        btns.addWidget(self.restore_btn)
        btns.addStretch(1)
        btns.addWidget(close)
        lay.addLayout(btns)
        self._load()

    def _load(self, select_row: int = 0) -> None:
        self.versions = self.ctx.versions.list(self.prompt_id)
        self.list.blockSignals(True)
        self.list.clear()
        for v in self.versions:
            label = f"نسخه‌ی {v.version_no} — {v.created_at.replace('T', ' ')}"
            if v.note:
                label += f"\n    {v.note}"
            self.list.addItem(QListWidgetItem(label))
        self.list.blockSignals(False)
        if self.versions:
            self.list.setCurrentRow(min(select_row, len(self.versions) - 1))
            self._show(self.list.currentRow())

    def _show(self, row: int) -> None:
        if row < 0 or row >= len(self.versions):
            return
        v = self.versions[row]
        self.note.setText(v.note)
        mode = self.mode.currentIndex()
        if mode == 0:
            self.view.setPlainText(f"{v.title}\n\n{v.body}")
        elif mode == 1:
            cur = self.ctx.prompts.get(self.prompt_id)
            self.view.setHtml(VersionService.diff_html(v.body, cur.body if cur else ""))
        else:
            prev = self.versions[row + 1] if row + 1 < len(self.versions) else None
            self.view.setHtml(VersionService.diff_html(prev.body if prev else "", v.body))

    def _save_note(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.ctx.versions.set_note(self.versions[row].id, self.note.text().strip())
            self._load(row)

    def _restore(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        v = self.versions[row]
        if confirm(self, "بازیابی نسخه",
                   f"متن نسخه‌ی {v.version_no} جایگزین متن فعلی می‌شود.\n"
                   "نسخه‌ی فعلی هم در تاریخچه می‌ماند و چیزی از بین نمی‌رود.", "بازیابی کن"):
            self.ctx.versions.restore(self.prompt_id, v.version_no)
            self.restored = True
            self._load(0)


# ---------------------------------------------------------------- مقایسه‌ی دو پرامپت
class CompareDialog(QDialog):
    def __init__(self, ctx: AppContext, left_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("مقایسه‌ی پرامپت‌ها")
        self.resize(1000, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.a = QComboBox()
        self.b = QComboBox()
        prompts = ctx.search.search()
        for p in prompts:
            self.a.addItem(p.title, p.id)
            self.b.addItem(p.title, p.id)
        select_combo_data(self.a, left_id)
        if self.b.count() > 1:
            self.b.setCurrentIndex(1 if self.b.itemData(0) == left_id else 0)
        for c in (self.a, self.b):
            c.currentIndexChanged.connect(self._refresh)
        top.addWidget(self.a, 1)
        top.addWidget(QLabel("⇄"))
        top.addWidget(self.b, 1)
        lay.addLayout(top)
        self.diff = QCheckBox("نمایش تفاوت‌ها به‌صورت رنگی")
        self.diff.toggled.connect(self._refresh)
        lay.addWidget(self.diff)
        split = QSplitter(Qt.Horizontal)
        self.va, self.vb = QTextBrowser(), QTextBrowser()
        split.addWidget(self.va)
        split.addWidget(self.vb)
        lay.addWidget(split, 1)
        close = QPushButton("بستن")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignLeft)
        self._refresh()

    def _refresh(self, *_) -> None:
        pa = self.ctx.prompts.get(self.a.currentData()) if self.a.currentData() else None
        pb = self.ctx.prompts.get(self.b.currentData()) if self.b.currentData() else None
        ta = pa.body if pa else ""
        tb = pb.body if pb else ""
        if self.diff.isChecked():
            self.va.setHtml(VersionService.diff_html(tb, ta))
            self.vb.setHtml(VersionService.diff_html(ta, tb))
        else:
            self.va.setPlainText(ta)
            self.vb.setPlainText(tb)


# ---------------------------------------------------------------- پیش‌نمایش بازیابی
class ImportPreviewDialog(QDialog):
    """نمایش پیش‌نمایش بسته‌ی بکاپ، تعارض‌ها و گرفتن تصمیم کاربر. هیچ تغییری تا تأیید نهایی اعمال نمی‌شود."""

    STATUS_FA = {im.NEW: "جدید", im.IDENTICAL: "یکسان (نادیده گرفته می‌شود)",
                 im.CHANGED: "تفاوت دارد", im.SIMILAR: "مشابه"}

    def __init__(self, ctx: AppContext, pkg: im.Package, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx, self.pkg = ctx, pkg
        self.preview = ctx.importer.preview(pkg)
        self.setWindowTitle("پیش‌نمایش بازیابی")
        self.resize(820, 620)
        lay = QVBoxLayout(self)
        c = self.preview.counts
        m = pkg.manifest
        lay.addWidget(QLabel(
            f"<b>فایل:</b> {pkg.path.name} &nbsp;|&nbsp; <b>ساخته‌شده:</b> {str(m.get('created_at', '؟')).replace('T', ' ')}"
            f" &nbsp;|&nbsp; <b>نسخه‌ی برنامه:</b> {m.get('app_version', '؟')}"))
        lay.addWidget(QLabel(
            f"پرامپت‌ها: {c['prompts']} — جدید: {c[im.NEW]} | یکسان: {c[im.IDENTICAL]} | "
            f"تفاوت‌دار: {c[im.CHANGED]} | مشابه: {c[im.SIMILAR]}<br>"
            f"قالب‌ها: {c['templates']} | دسته‌بندی‌های جدید: {self.preview.categories_new} | "
            f"برچسب‌های جدید: {self.preview.tags_new}"))
        if pkg.kind == "json":
            n = QLabel("⚠️ این فایل JSON است؛ پیوست‌ها (فایل‌ها) در آن نیست. برای انتقال کامل از .pvault استفاده کنید.")
            n.setWordWrap(True)
            lay.addWidget(n)

        self.mode_merge = QRadioButton("ادغام با اطلاعات فعلی (پیشنهادی — چیزی حذف نمی‌شود)")
        self.mode_replace = QRadioButton("جایگزینی کامل (تمام اطلاعات فعلی با محتوای این بکاپ عوض می‌شود)")
        self.mode_merge.setChecked(True)
        lay.addWidget(self.mode_merge)
        lay.addWidget(self.mode_replace)

        self.table = QListWidget()
        self.combos: dict[str, QComboBox] = {}
        conflicts = self.preview.conflicts
        if conflicts:
            lay.addWidget(QLabel("برای موارد تکراری یا مشابه تصمیم بگیرید:"))
            default_row = QHBoxLayout()
            default_row.addWidget(QLabel("برای همه:"))
            self.default_combo = QComboBox()
            self._fill_actions(self.default_combo)
            self.default_combo.currentIndexChanged.connect(self._apply_default)
            default_row.addWidget(self.default_combo)
            default_row.addStretch(1)
            lay.addLayout(default_row)
            for it in conflicts:
                row = QListWidgetItem()
                w = QWidget()
                hl = QHBoxLayout(w)
                kind = "پرامپت" if it.kind == "prompt" else "قالب"
                lab = QLabel(f"{kind}: <b>{it.title}</b> — {self.STATUS_FA[it.status]}"
                             f"{(' (' + it.reason + ')') if it.reason else ''}")
                lab.setWordWrap(True)
                cb = QComboBox()
                self._fill_actions(cb)
                self.combos[it.uuid] = cb
                hl.addWidget(lab, 1)
                hl.addWidget(cb)
                row.setSizeHint(w.sizeHint())
                self.table.addItem(row)
                self.table.setItemWidget(row, w)
            lay.addWidget(self.table, 1)
        else:
            lay.addWidget(QLabel("✅ تعارضی وجود ندارد."))
            lay.addStretch(1)
            self.default_combo = None

        self.settings_cb = QCheckBox("تنظیمات شخصی (تم، فونت و ...) هم وارد شود")
        self.settings_cb.setEnabled(self.preview.settings_included)
        lay.addWidget(self.settings_cb)
        bb = QDialogButtonBox()
        ok = bb.addButton("شروع بازیابی", QDialogButtonBox.AcceptRole)
        ok.setObjectName("primary")
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @staticmethod
    def _fill_actions(cb: QComboBox) -> None:
        cb.addItem("نگه داشتن نسخه‌ی فعلی (رد کردن)", im.SKIP)
        cb.addItem("جایگزین شود (متن قبلی در تاریخچه می‌ماند)", im.REPLACE)
        cb.addItem("هر دو نگه داشته شوند", im.BOTH)

    def _apply_default(self) -> None:
        data = self.default_combo.currentData()
        for cb in self.combos.values():
            select_combo_data(cb, data)

    def _accept(self) -> None:
        if self.mode_replace.isChecked() and not confirm(
                self, "جایگزینی کامل",
                "تمام پرامپت‌ها، دسته‌بندی‌ها و قالب‌های فعلی حذف و با محتوای این بکاپ جایگزین می‌شوند.\n"
                "قبل از شروع، یک بکاپ ایمنی از وضعیت فعلی گرفته می‌شود.", "ادامه بده", danger=True):
            return
        self.accept()

    def options(self) -> dict:
        return {
            "mode": "replace_all" if self.mode_replace.isChecked() else "merge",
            "decisions": {u: cb.currentData() for u, cb in self.combos.items()},
            "default_action": im.SKIP,
            "import_settings": self.settings_cb.isChecked(),
        }


# ---------------------------------------------------------------- پر کردن قالب
class TemplateFillDialog(QDialog):
    """گرفتن مقدار متغیرهای {{VAR}} و ساخت متن نهایی با پیش‌نمایش زنده."""

    def __init__(self, template_body: str, parent: QWidget | None = None, title: str = "ساخت پرامپت از قالب"):
        super().__init__(parent)
        self.body = template_body
        self.setWindowTitle(title)
        self.resize(780, 560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.fields: dict[str, QLineEdit] = {}
        for var in extract_variables(template_body):
            le = QLineEdit()
            le.setPlaceholderText(f"مقدار {{{{{var}}}}}")
            le.textChanged.connect(self._update)
            self.fields[var] = le
            form.addRow(var, le)
        if self.fields:
            lay.addLayout(form)
        else:
            lay.addWidget(QLabel("این قالب متغیری ندارد."))
        lay.addWidget(QLabel("پیش‌نمایش پرامپت نهایی:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        lay.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.copy_btn = QPushButton("کپی متن نهایی")
        self.save_btn = QPushButton("ذخیره به‌عنوان پرامپت جدید")
        self.save_btn.setObjectName("primary")
        close = QPushButton("بستن")
        row.addWidget(self.copy_btn)
        row.addWidget(self.save_btn)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        close.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.accept)
        self.copy_btn.clicked.connect(lambda: copy_to_clipboard(self.result_text()))
        self._update()

    def values(self) -> dict[str, str]:
        return {k: v.text() for k, v in self.fields.items()}

    def result_text(self) -> str:
        return render(self.body, self.values())

    def _update(self) -> None:
        self.preview.setPlainText(self.result_text())


def ask_text(parent: QWidget, title: str, label: str, text: str = "") -> str | None:
    value, ok = QInputDialog.getText(parent, title, label, QLineEdit.Normal, text)
    value = value.strip()
    return value if ok and value else None
