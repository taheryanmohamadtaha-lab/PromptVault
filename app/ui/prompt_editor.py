"""ویرایشگر پرامپت: ذخیره‌ی خودکار، شمارش کلمات، Markdown، پیوست‌ها، نسخه‌ها و پرامپت‌های مشابه."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QStackedWidget, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from ..core.context import AppContext
from ..models.prompt import IMPORTANCE_LABELS, STATUSES
from ..utils.text import char_count, word_count
from .dialogs import (
    VersionHistoryDialog, confirm, copy_to_clipboard, error, fill_category_combo, info, select_combo_data,
)
from .result_panel import ResultPanel, open_attachment_safely

AUTOSAVE_MS = 1500


class PromptEditorDialog(QDialog):
    saved = Signal(int)   # شناسه‌ی پرامپت ذخیره‌شده

    def __init__(self, ctx: AppContext, prompt_id: int | None = None, parent: QWidget | None = None,
                 category_id: int | None = None, initial_title: str = "", initial_body: str = ""):
        super().__init__(parent)
        self.ctx = ctx
        self.prompt_id = prompt_id
        self._loading = True
        self._dirty = False
        self._zoom = int(ctx.settings.get("editor_font_size") or 12)
        self.setWindowTitle("ویرایش پرامپت" if prompt_id else "پرامپت جدید")
        self.setLayoutDirection(Qt.RightToLeft)
        self._fit_to_screen()
        self._build()
        if prompt_id:
            self._load(prompt_id)
        else:
            select_combo_data(self.category, category_id)
            self.title.setText(initial_title)
            self.body.setPlainText(initial_body)
        self._loading = False
        self._dirty = False
        self._update_counts()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._autosave)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_now)
        self.title.setFocus()

    def _fit_to_screen(self) -> None:
        """اندازه‌ی پنجره بر اساس مانیتور: هرگز بزرگ‌تر از ناحیه‌ی قابل‌استفاده‌ی صفحه نمی‌شود."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1000, 640)
            return
        avail = screen.availableGeometry()
        w = min(1180, int(avail.width() * 0.94))
        h = min(780, int(avail.height() * 0.90))
        self.setMinimumSize(min(640, w), min(420, h))
        self.resize(w, h)
        self.move(avail.center().x() - w // 2, avail.center().y() - h // 2)

    # ---------------------------------------------------------------- UI
    def _build(self) -> None:
        root = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        # ---- ستون اصلی (متن)
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 8, 0)
        self.title = QLineEdit()
        self.title.setPlaceholderText("عنوان پرامپت …")
        self.title.setStyleSheet("font-size: 15pt; font-weight: 600;")
        ml.addWidget(self.title)

        bar = QHBoxLayout()
        self.copy_btn = QPushButton("📋 کپی پرامپت")
        self.copy_btn.setObjectName("primary")
        self.copy_btn.clicked.connect(self.copy_prompt)
        self.paste_btn = QPushButton("از کلیپ‌بورد")
        self.paste_btn.setToolTip("جایگزینی متن با محتوای کلیپ‌بورد")
        self.paste_btn.clicked.connect(self.paste_clipboard)
        self.md_btn = QPushButton("پیش‌نمایش Markdown")
        self.md_btn.setCheckable(True)
        self.md_btn.toggled.connect(self._toggle_md)
        zin, zout = QPushButton("＋"), QPushButton("－")
        zin.setToolTip("بزرگ‌نمایی")
        zout.setToolTip("کوچک‌نمایی")
        zin.clicked.connect(lambda: self._set_zoom(self._zoom + 1))
        zout.clicked.connect(lambda: self._set_zoom(self._zoom - 1))
        self.top_save_btn = QPushButton("💾 ذخیره")
        self.top_save_btn.setToolTip("ذخیره (Ctrl+S) — پنجره باز می‌ماند")
        self.top_save_btn.clicked.connect(self.save_now)
        for w in (self.copy_btn, self.top_save_btn, self.paste_btn, self.md_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(zout)
        bar.addWidget(zin)
        ml.addLayout(bar)

        self.stack = QStackedWidget()
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText("متن کامل پرامپت را اینجا بنویسید یا جای‌گذاری کنید …")
        self.body.setTabStopDistance(32)
        self.body.setLineWrapMode(
            QPlainTextEdit.WidgetWidth if self.ctx.settings.get("editor_wrap") else QPlainTextEdit.NoWrap)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.stack.addWidget(self.body)
        self.stack.addWidget(self.preview)
        ml.addWidget(self.stack, 1)
        self._set_zoom(self._zoom)

        foot = QHBoxLayout()
        self.counts = QLabel()
        self.counts.setObjectName("muted")
        self.status = QLabel("")
        self.status.setObjectName("muted")
        foot.addWidget(self.counts)
        foot.addStretch(1)
        foot.addWidget(self.status)
        ml.addLayout(foot)
        split.addWidget(main)

        # ---- ستون کناری (مشخصات)
        side = QTabWidget()
        meta = QWidget()
        form = QFormLayout(meta)
        self.category = QComboBox()
        fill_category_combo(self.category, self.ctx)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("با ویرگول جدا کنید: AI، اندروید، MT5")
        self.platform = QComboBox()
        self.platform.setEditable(True)
        self.platform.addItems(["", "ChatGPT", "Claude", "Gemini", "Midjourney", "DALL·E", "Stable Diffusion",
                                "Copilot", "Grok", "DeepSeek", "Runway", "Sora", "Veo"])
        for p in self.ctx.search.platforms():
            if self.platform.findText(p) < 0:
                self.platform.addItem(p)
        self.output = QLineEdit()
        self.output.setPlaceholderText("متن، تصویر، ویدیو، کد، …")
        self.status_box = QComboBox()
        self.status_box.addItems(STATUSES)
        self.importance = QComboBox()
        for k in sorted(IMPORTANCE_LABELS):
            self.importance.addItem(IMPORTANCE_LABELS[k], k)
        self.importance.setCurrentIndex(1)
        self.favorite = QCheckBox("⭐ موردعلاقه")
        self.pinned = QCheckBox("📌 سنجاق‌شده")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("توضیحات شخصی …")
        self.notes.setFixedHeight(90)
        self.info_lbl = QLabel("")
        self.info_lbl.setObjectName("muted")
        self.info_lbl.setWordWrap(True)
        form.addRow("دسته‌بندی", self.category)
        form.addRow("برچسب‌ها", self.tags)
        form.addRow("پلتفرم AI", self.platform)
        form.addRow("نوع خروجی", self.output)
        form.addRow("وضعیت", self.status_box)
        form.addRow("اهمیت", self.importance)
        form.addRow(self.favorite)
        form.addRow(self.pinned)
        form.addRow("توضیحات", self.notes)
        form.addRow(self.info_lbl)
        meta_scroll = QScrollArea()
        meta_scroll.setWidgetResizable(True)
        meta_scroll.setFrameShape(QFrame.NoFrame)
        meta_scroll.setWidget(meta)
        side.addTab(meta_scroll, "مشخصات")

        # تصویر و نتیجه‌ی نهایی
        self.result_panel = ResultPanel(self.ctx, lambda: self.prompt_id, self._ensure_saved)
        self.result_panel.message.connect(self.status.setText)
        side.addTab(self.result_panel, "🖼 تصویر و نتیجه")
        self.side_tabs = side

        # پیوست‌ها
        att = QWidget()
        al = QVBoxLayout(att)
        self.att_list = QListWidget()
        self.att_list.itemDoubleClicked.connect(lambda _i: self.open_attachment())
        al.addWidget(self.att_list, 1)
        row = QHBoxLayout()
        b_add, b_open, b_del = QPushButton("افزودن فایل"), QPushButton("باز کردن"), QPushButton("حذف")
        b_del.setObjectName("danger")
        b_add.clicked.connect(self.add_attachment)
        b_open.clicked.connect(self.open_attachment)
        b_del.clicked.connect(self.remove_attachment)
        for b in (b_add, b_open, b_del):
            row.addWidget(b)
        al.addLayout(row)
        side.addTab(att, "سایر پیوست‌ها")

        # نسخه‌ها و مشابه‌ها
        extra = QWidget()
        el = QVBoxLayout(extra)
        self.versions_btn = QPushButton("🕘 تاریخچه‌ی نسخه‌ها و مقایسه")
        self.versions_btn.clicked.connect(self.open_versions)
        self.snapshot_btn = QPushButton("ثبت نسخه‌ی جدید با توضیح")
        self.snapshot_btn.clicked.connect(self.save_version_with_note)
        el.addWidget(self.versions_btn)
        el.addWidget(self.snapshot_btn)
        el.addWidget(QLabel("پرامپت‌های مشابه:"))
        self.similar_list = QListWidget()
        el.addWidget(self.similar_list, 1)
        side.addTab(extra, "نسخه‌ها و مشابه")
        split.addWidget(side)
        split.setSizes([700, 460])
        split.setChildrenCollapsible(False)

        # دکمه‌های پایین
        bottom = QHBoxLayout()
        self.save_btn = QPushButton("ذخیره و بستن")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self.save_and_close)
        cancel = QPushButton("بستن")
        cancel.clicked.connect(self.close)
        bottom.addStretch(1)
        bottom.addWidget(cancel)
        bottom.addWidget(self.save_btn)
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(split, 1)
        wl.addLayout(bottom)
        root.removeWidget(split)
        root.addWidget(wrapper)

        for w in (self.title, self.tags, self.output):
            w.textChanged.connect(self._changed)
        self.platform.editTextChanged.connect(self._changed)
        self.body.textChanged.connect(self._changed)
        self.notes.textChanged.connect(self._changed)
        for c in (self.category, self.status_box, self.importance):
            c.currentIndexChanged.connect(self._changed)
        for c in (self.favorite, self.pinned):
            c.toggled.connect(self._changed)

    # ---------------------------------------------------------------- بارگذاری / ذخیره
    def _load(self, pid: int) -> None:
        p = self.ctx.prompts.get(pid)
        if p is None:
            error(self, "خطا", "این پرامپت دیگر وجود ندارد.")
            QTimer.singleShot(0, self.reject)
            return
        self.title.setText(p.title)
        self.body.setPlainText(p.body)
        select_combo_data(self.category, p.category_id)
        self.tags.setText("، ".join(p.tags))
        self.platform.setCurrentText(p.platform)
        self.output.setText(p.output_type)
        self.status_box.setCurrentText(p.status)
        select_combo_data(self.importance, p.importance)
        self.favorite.setChecked(p.favorite)
        self.pinned.setChecked(p.pinned)
        self.notes.setPlainText(p.notes)
        self._refresh_side()

    def _refresh_side(self) -> None:
        self.att_list.clear()
        self.similar_list.clear()
        if not self.prompt_id:
            self.info_lbl.setText("")
            self.result_panel.refresh()
            return
        p = self.ctx.prompts.get(self.prompt_id)
        if p:
            self.info_lbl.setText(
                f"ایجاد: {p.created_at.replace('T', ' ')}\nآخرین ویرایش: {p.updated_at.replace('T', ' ')}\n"
                f"تعداد استفاده: {p.use_count}"
                + (f"\nآخرین استفاده: {p.last_used_at.replace('T', ' ')}" if p.last_used_at else ""))
        self.result_panel.refresh()
        for a in self.ctx.files.list(self.prompt_id, "file"):
            it = QListWidgetItem(f"📎 {a.filename}  ({a.size // 1024 + 1} KB)")
            it.setData(Qt.UserRole, a.id)
            if not self.ctx.files.exists(a):
                it.setText(it.text() + "  — فایل پیدا نشد")
            self.att_list.addItem(it)
        for s in self.ctx.prompts.similar(self.prompt_id):
            it = QListWidgetItem(s.title)
            it.setData(Qt.UserRole, s.id)
            self.similar_list.addItem(it)

    def _collect(self) -> dict:
        return dict(
            title=self.title.text().strip(),
            body=self.body.toPlainText(),
            category_id=self.category.currentData(),
            platform=self.platform.currentText().strip(),
            output_type=self.output.text().strip(),
            notes=self.notes.toPlainText(),
            status=self.status_box.currentText(),
            importance=self.importance.currentData() or 2,
            favorite=self.favorite.isChecked(),
            pinned=self.pinned.isChecked(),
        )

    def _tag_list(self) -> list[str]:
        raw = self.tags.text().replace("،", ",").replace("؛", ",").replace(";", ",")
        return [t.strip() for t in raw.split(",") if t.strip()]

    def _persist(self, record_version: bool) -> bool:
        """ذخیره در دیتابیس. اگر هنوز عنوان ندارد ذخیره نمی‌شود (False)."""
        data = self._collect()
        if not data["title"]:
            return False
        try:
            if self.prompt_id is None:
                cid = data.pop("category_id")
                p = self.ctx.prompts.create(data.pop("title"), data.pop("body"), cid, self._tag_list(), **data)
                self.prompt_id = p.id
                self.setWindowTitle("ویرایش پرامپت")
                self._refresh_side()
            else:
                self.ctx.prompts.update(self.prompt_id, tags=self._tag_list(), record_version=record_version, **data)
        except Exception as e:  # noqa: BLE001
            self.status.setText("⚠️ ذخیره نشد")
            error(self, "خطا در ذخیره", str(e))
            return False
        self._dirty = False
        self.saved.emit(self.prompt_id)
        return True

    def _changed(self, *_a) -> None:
        if self._loading:
            return
        self._dirty = True
        self._update_counts()
        if self.stack.currentIndex() == 1:
            self.preview.setMarkdown(self.body.toPlainText())
        if self.ctx.settings.get("editor_autosave"):
            self.status.setText("در حال ویرایش …")
            self._timer.start(AUTOSAVE_MS)
        else:
            self.status.setText("ذخیره نشده — Ctrl+S")

    def _autosave(self) -> None:
        if self._dirty and self._persist(record_version=False):
            self.status.setText("✓ ذخیره شد (خودکار)")

    def save_now(self) -> bool:
        ok = self._persist(record_version=False)
        if ok:
            self.ctx.prompts.commit_version(self.prompt_id)
            self.status.setText("✓ ذخیره شد")
        elif not self.title.text().strip():
            info(self, "عنوان لازم است", "برای ذخیره، یک عنوان برای پرامپت بنویسید.")
        return ok

    def save_and_close(self) -> None:
        if self.save_now():
            self.accept()

    def closeEvent(self, ev) -> None:  # noqa: N802
        self._timer.stop()
        if self._dirty and self.title.text().strip():
            self._persist(record_version=False)
            if self.prompt_id:
                self.ctx.prompts.commit_version(self.prompt_id)
        elif self._dirty and not self.title.text().strip() and (
                self.body.toPlainText().strip()):
            if not confirm(self, "بدون عنوان", "این پرامپت عنوان ندارد و ذخیره نمی‌شود. بسته شود؟", "بستن بدون ذخیره"):
                ev.ignore()
                return
        super().closeEvent(ev)

    def done(self, r: int) -> None:  # noqa: D401
        if self._dirty and self.title.text().strip() and r != QDialog.Accepted:
            self._persist(record_version=False)
            if self.prompt_id:
                self.ctx.prompts.commit_version(self.prompt_id)
        super().done(r)

    # ---------------------------------------------------------------- ابزارها
    def _update_counts(self) -> None:
        t = self.body.toPlainText()
        self.counts.setText(f"{word_count(t)} کلمه • {char_count(t)} کاراکتر")

    def _set_zoom(self, size: int) -> None:
        self._zoom = max(8, min(36, size))
        f = self.body.font()
        f.setPointSize(self._zoom)
        self.body.setFont(f)
        self.preview.setFont(f)
        self.ctx.settings.set("editor_font_size", self._zoom)

    def _toggle_md(self, on: bool) -> None:
        if on:
            self.preview.setMarkdown(self.body.toPlainText())
        self.stack.setCurrentIndex(1 if on else 0)

    def copy_prompt(self) -> None:
        copy_to_clipboard(self.body.toPlainText())
        if self.prompt_id:
            self.ctx.prompts.mark_used(self.prompt_id)
            self._refresh_side()
        self.status.setText("✓ پرامپت کپی شد")
        top = self.window()
        if hasattr(top, "toast"):
            top.toast("پرامپت کپی شد")

    def paste_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        if not text:
            info(self, "کلیپ‌بورد خالی است", "متنی در کلیپ‌بورد پیدا نشد.")
            return
        if self.body.toPlainText().strip() and not confirm(
                self, "جایگزینی متن", "متن فعلی با محتوای کلیپ‌بورد جایگزین شود؟ (نسخه‌ی قبلی در تاریخچه می‌ماند)",
                "جایگزین کن"):
            return
        if self.prompt_id:
            self._persist(record_version=False)
            self.ctx.prompts.commit_version(self.prompt_id, "پیش از جای‌گذاری از کلیپ‌بورد")
        self.body.setPlainText(text)

    # ---------------------------------------------------------------- پیوست‌ها
    def _ensure_saved(self) -> bool:
        if self.prompt_id:
            return True
        if not self.title.text().strip():
            info(self, "ابتدا عنوان بنویسید", "برای افزودن پیوست، اول یک عنوان برای پرامپت وارد کنید.")
            return False
        return self._persist(record_version=False)

    def add_attachment(self) -> None:
        if not self._ensure_saved():
            return
        files, _ = QFileDialog.getOpenFileNames(self, "انتخاب فایل پیوست", "", "همه‌ی فایل‌ها (*.*)")
        for f in files:
            try:
                self.ctx.files.add(self.prompt_id, f, kind="file")
            except Exception as e:  # noqa: BLE001
                error(self, "پیوست ناموفق", f"{Path(f).name}\n{e}")
        self._refresh_side()

    def _current_att(self):
        it = self.att_list.currentItem()
        return self.ctx.files.get(it.data(Qt.UserRole)) if it else None

    def open_attachment(self) -> None:
        a = self._current_att()
        if a is None:
            return
        open_attachment_safely(self.ctx, a, self)

    def remove_attachment(self) -> None:
        a = self._current_att()
        if a and confirm(self, "حذف پیوست", f"پیوست «{a.filename}» حذف شود؟", "حذف کن", danger=True):
            self.ctx.files.delete(a.id)
            self._refresh_side()

    # ---------------------------------------------------------------- نسخه‌ها
    def open_versions(self) -> None:
        if not self.prompt_id:
            info(self, "هنوز ذخیره نشده", "ابتدا پرامپت را ذخیره کنید.")
            return
        self._persist(record_version=False)
        self.ctx.prompts.commit_version(self.prompt_id)
        dlg = VersionHistoryDialog(self.ctx, self.prompt_id, self)
        dlg.exec()
        if dlg.restored:
            self._loading = True
            self._load(self.prompt_id)
            self._loading = False
            self._update_counts()

    def save_version_with_note(self) -> None:
        from .dialogs import ask_text
        if not self._ensure_saved():
            return
        note = ask_text(self, "نسخه‌ی جدید", "توضیح این نسخه:")
        if note is None:
            return
        self._persist(record_version=False)
        if not self.ctx.prompts.commit_version(self.prompt_id, note):
            info(self, "تغییری نیست", "متن از آخرین نسخه‌ی ثبت‌شده تغییری نکرده است.")
        else:
            self.status.setText("✓ نسخه ثبت شد")
