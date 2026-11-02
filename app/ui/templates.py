"""قالب‌های آماده‌ی پرامپت با متغیرهای {{NAME}}."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..core.context import AppContext
from ..services.template_service import extract_variables
from .dialogs import TemplateFillDialog, confirm, error, fill_category_combo, select_combo_data


class TemplatesPage(QWidget):
    changed = Signal()
    message = Signal(str)
    create_prompt = Signal(str, str, object)   # عنوان، متن نهایی، شناسه‌ی دسته (یا None) → باز کردن ویرایشگر

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self._current_id: int | None = None
        self._loading = False
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 14)
        head = QHBoxLayout()
        t = QLabel("قالب‌های آماده")
        t.setObjectName("h1")
        head.addWidget(t)
        head.addStretch(1)
        self.new_btn = QPushButton("➕ قالب جدید")
        self.new_btn.setObjectName("primary")
        self.new_btn.clicked.connect(self._new)
        head.addWidget(self.new_btn)
        root.addLayout(head)
        hint = QLabel("در متن قالب هر جا که لازم است از {{نام_متغیر}} استفاده کنید؛ مثل {{APP_NAME}}. "
                      "هنگام استفاده، برنامه مقدار هر متغیر را می‌پرسد و پرامپت نهایی را می‌سازد.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        root.addWidget(hint)

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._selected)
        split.addWidget(self.list)

        panel = QFrame()
        panel.setObjectName("panel")
        pl = QVBoxLayout(panel)
        form = QFormLayout()
        self.title = QLineEdit()
        self.title.setPlaceholderText("عنوان قالب")
        self.desc = QLineEdit()
        self.desc.setPlaceholderText("توضیح کوتاه (اختیاری)")
        self.category = QComboBox()
        form.addRow("عنوان:", self.title)
        form.addRow("توضیح:", self.desc)
        form.addRow("دسته‌بندی پیشنهادی:", self.category)
        pl.addLayout(form)
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText("متن قالب … مثال:\nیک اپلیکیشن به نام {{APP_NAME}} برای {{PLATFORM}} بساز.")
        self.body.textChanged.connect(self._update_vars)
        pl.addWidget(self.body, 1)
        self.vars_label = QLabel("")
        self.vars_label.setObjectName("muted")
        self.vars_label.setWordWrap(True)
        pl.addWidget(self.vars_label)
        row = QHBoxLayout()
        self.save_btn = QPushButton("💾 ذخیره‌ی قالب")
        self.save_btn.setObjectName("primary")
        self.use_btn = QPushButton("⚡ استفاده از قالب")
        self.dup_btn = QPushButton("⧉ تکثیر")
        self.del_btn = QPushButton("🗑️ حذف")
        self.del_btn.setObjectName("danger")
        self.save_btn.clicked.connect(self._save)
        self.use_btn.clicked.connect(self._use)
        self.dup_btn.clicked.connect(self._duplicate)
        self.del_btn.clicked.connect(self._delete)
        for b in (self.save_btn, self.use_btn, self.dup_btn):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.del_btn)
        pl.addLayout(row)
        split.addWidget(panel)
        split.setSizes([300, 700])
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)
        self._set_editing(False)

    # ---------------------------------------------------------------- نمایش
    def refresh(self) -> None:
        keep = self._current_id
        self._loading = True
        fill_category_combo(self.category, self.ctx, include_none="بدون دسته‌بندی")
        self.list.clear()
        for tpl in self.ctx.templates.list():
            it = QListWidgetItem(tpl.title)
            it.setData(Qt.UserRole, tpl.id)
            it.setToolTip(tpl.description)
            self.list.addItem(it)
            if tpl.id == keep:
                self.list.setCurrentItem(it)
        self._loading = False
        if self.list.currentItem() is None:
            self._current_id = None
            self._clear_form()
        else:
            self._selected(self.list.currentItem(), None)

    def _set_editing(self, on: bool) -> None:
        for w in (self.title, self.desc, self.category, self.body, self.save_btn):
            w.setEnabled(on)
        for w in (self.use_btn, self.dup_btn, self.del_btn):
            w.setEnabled(on and self._current_id is not None)

    def _clear_form(self) -> None:
        self._loading = True
        self.title.clear()
        self.desc.clear()
        self.body.clear()
        select_combo_data(self.category, None)
        self._loading = False
        self.vars_label.setText("")
        self._set_editing(False)

    def _selected(self, item: QListWidgetItem | None, _prev) -> None:
        if self._loading:
            return
        if item is None:
            self._current_id = None
            self._clear_form()
            return
        tpl = self.ctx.templates.get(item.data(Qt.UserRole))
        if tpl is None:
            return
        self._current_id = tpl.id
        self._loading = True
        self.title.setText(tpl.title)
        self.desc.setText(tpl.description)
        self.body.setPlainText(tpl.body)
        select_combo_data(self.category, tpl.category_id)
        self._loading = False
        self._set_editing(True)
        self._update_vars()

    def _update_vars(self) -> None:
        names = extract_variables(self.body.toPlainText())
        self.vars_label.setText(
            "متغیرهای این قالب: " + "  ".join("{{" + n + "}}" for n in names) if names
            else "این قالب هنوز متغیری ندارد.")

    # ---------------------------------------------------------------- عملیات
    def _new(self) -> None:
        try:
            tpl = self.ctx.templates.create("قالب جدید", "", "", None)
        except ValueError as e:
            error(self, "ساخت قالب ممکن نشد", str(e))
            return
        self._current_id = tpl.id
        self.changed.emit()
        self.refresh()
        self.title.setFocus()
        self.title.selectAll()

    def _save(self) -> bool:
        if self._current_id is None:
            return False
        try:
            self.ctx.templates.update(self._current_id, self.title.text(), self.body.toPlainText(),
                                      self.desc.text(), self.category.currentData())
        except (ValueError, KeyError) as e:
            error(self, "ذخیره ممکن نشد", str(e))
            return False
        self.message.emit("قالب ذخیره شد")
        self.changed.emit()
        self.refresh()
        return True

    def _use(self) -> None:
        if self._current_id is None or not self._save():
            return
        dlg = TemplateFillDialog(self.body.toPlainText(), self, "ساخت پرامپت از قالب: " + self.title.text())
        if dlg.exec():
            self.create_prompt.emit(self.title.text(), dlg.result_text(), self.category.currentData())

    def _duplicate(self) -> None:
        if self._current_id is None:
            return
        new = self.ctx.templates.duplicate(self._current_id)
        self._current_id = new.id
        self.changed.emit()
        self.refresh()

    def _delete(self) -> None:
        if self._current_id is None:
            return
        if confirm(self, "حذف قالب", f"قالب «{self.title.text()}» حذف شود؟ (پرامپت‌هایی که قبلاً از آن ساخته‌اید می‌مانند)",
                   "حذف قالب", danger=True):
            self.ctx.templates.delete(self._current_id)
            self._current_id = None
            self.changed.emit()
            self.refresh()
