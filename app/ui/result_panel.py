"""پنل «تصویر و نتیجه‌ی نهایی» کنار پرامپت.

- تصویر برنامه/اندیکاتور ساخته‌شده (اسکرین‌شات): افزودن از فایل، از کلیپ‌بورد یا با کشیدن و رها کردن
- کد یا فایل نهایی که هوش مصنوعی ساخته: افزودن فایل، چسباندن کد از کلیپ‌بورد، مشاهده، کپی و ذخیره
همه‌چیز به‌صورت پیوست (با نوع image / result) در پوشه‌ی مدیریت‌شده‌ی برنامه نگه‌داری می‌شود و در بکاپ می‌آید.
"""
from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..core.context import AppContext
from ..services.file_service import IMAGE_EXTENSIONS
from .dialogs import ask_text, confirm, copy_to_clipboard, error, info

IMAGE_FILTER = "تصویر (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"


def open_attachment_safely(ctx: AppContext, att, parent: QWidget) -> None:
    """فایل‌های امن با برنامه‌ی پیش‌فرض باز می‌شوند؛ برای کد/اسکریپت فقط پوشه باز می‌شود (تا چیزی اجرا نشود)."""
    if not ctx.files.exists(att):
        error(parent, "فایل پیدا نشد", "فایل از پوشه‌ی برنامه حذف شده است.")
        return
    path = ctx.files.path_of(att)
    if ctx.files.is_safe_to_open(att):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        info(parent, "باز کردن پوشه",
             "برای امنیت، فایل‌های کد و اسکریپت اجرا نمی‌شوند. پوشه‌ی ذخیره باز شد؛ "
             "برای دیدن متن از پیش‌نمایش داخل برنامه و برای ذخیره از «ذخیره به‌عنوان» استفاده کنید.")


class ResultPanel(QWidget):
    message = Signal(str)     # پیام کوتاه وضعیت برای پنجره‌ی میزبان

    def __init__(self, ctx: AppContext, get_prompt_id: Callable[[], int | None],
                 ensure_saved: Callable[[], bool], parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self._pid = get_prompt_id
        self._ensure = ensure_saved
        self._img_pix: QPixmap | None = None
        self.setAcceptDrops(True)
        self._build()
        self.refresh()

    # ---------------------------------------------------------------- UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        h1 = QLabel("🖼 تصویر برنامه / اندیکاتور")
        h1.setObjectName("h2")
        root.addWidget(h1)
        self.img_scroll = QScrollArea()
        self.img_scroll.setWidgetResizable(True)
        self.img_scroll.setMinimumHeight(140)
        self.img_view = QLabel()
        self.img_view.setAlignment(Qt.AlignCenter)
        self.img_view.setWordWrap(True)
        self.img_scroll.setWidget(self.img_view)
        root.addWidget(self.img_scroll, 3)

        self.img_list = QListWidget()
        self.img_list.setViewMode(QListView.IconMode)
        self.img_list.setFlow(QListView.LeftToRight)
        self.img_list.setWrapping(False)
        self.img_list.setMovement(QListView.Static)
        self.img_list.setIconSize(QSize(64, 64))
        self.img_list.setSpacing(4)
        self.img_list.setFixedHeight(96)
        self.img_list.currentItemChanged.connect(lambda cur, _prev: self._show_image(self._id_of(cur)))
        self.img_list.itemDoubleClicked.connect(lambda _i: self.open_image())
        root.addWidget(self.img_list)

        row = QHBoxLayout()
        for text, fn in (("افزودن تصویر", self.add_image), ("از کلیپ‌بورد", self.paste_image),
                         ("بزرگ‌نمایی", self.open_image), ("حذف", self.remove_image)):
            b = QPushButton(text)
            b.clicked.connect(lambda _c=False, f=fn: f())
            if text == "حذف":
                b.setObjectName("danger")
            row.addWidget(b)
        root.addLayout(row)

        h2 = QLabel("💾 کد / فایل نهایی (نتیجه‌ی هوش مصنوعی)")
        h2.setObjectName("h2")
        root.addWidget(h2)
        self.res_list = QListWidget()
        self.res_list.setMaximumHeight(84)
        self.res_list.currentItemChanged.connect(lambda cur, _prev: self._show_result(self._id_of(cur)))
        root.addWidget(self.res_list)
        self.res_view = QPlainTextEdit()
        self.res_view.setReadOnly(True)
        self.res_view.setAcceptDrops(False)
        self.res_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.res_view.setLayoutDirection(Qt.LeftToRight)
        self.res_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.res_view.setMinimumHeight(110)
        root.addWidget(self.res_view, 4)

        row1, row2 = QHBoxLayout(), QHBoxLayout()
        for lay, items in ((row1, (("افزودن فایل", self.add_result_file), ("چسباندن کد", self.paste_code),
                                   ("📋 کپی کد", self.copy_code))),
                           (row2, (("ذخیره به‌عنوان …", self.save_result_as), ("باز کردن", self.open_result),
                                   ("حذف", self.remove_result)))):
            for text, fn in items:
                b = QPushButton(text)
                b.clicked.connect(lambda _c=False, f=fn: f())
                if text == "حذف":
                    b.setObjectName("danger")
                lay.addWidget(b)
            root.addLayout(lay)

    # ---------------------------------------------------------------- نمایش
    @staticmethod
    def _id_of(item: QListWidgetItem | None) -> int | None:
        return item.data(Qt.UserRole) if item is not None else None

    def refresh(self, select_image: int | None = None, select_result: int | None = None) -> None:
        pid = self._pid()
        keep_img = select_image or self._id_of(self.img_list.currentItem())
        keep_res = select_result or self._id_of(self.res_list.currentItem())
        self.img_list.blockSignals(True)
        self.res_list.blockSignals(True)
        self.img_list.clear()
        self.res_list.clear()
        if pid:
            for a in self.ctx.files.list(pid, "image"):
                it = QListWidgetItem()
                it.setData(Qt.UserRole, a.id)
                it.setToolTip(a.filename)
                pm = QPixmap(str(self.ctx.files.path_of(a))) if self.ctx.files.exists(a) else QPixmap()
                if pm.isNull():
                    it.setText("؟")
                else:
                    it.setIcon(QIcon(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                self.img_list.addItem(it)
            for a in self.ctx.files.list(pid, "result"):
                suffix = "" if self.ctx.files.exists(a) else "  — فایل پیدا نشد"
                it = QListWidgetItem(f"📄 {a.filename}  ({a.size // 1024 + 1} KB){suffix}")
                it.setData(Qt.UserRole, a.id)
                self.res_list.addItem(it)
        self._select(self.img_list, keep_img)
        self._select(self.res_list, keep_res)
        self.img_list.blockSignals(False)
        self.res_list.blockSignals(False)
        self._show_image(self._id_of(self.img_list.currentItem()))
        self._show_result(self._id_of(self.res_list.currentItem()))

    @staticmethod
    def _select(widget: QListWidget, att_id: int | None) -> None:
        if widget.count() == 0:
            return
        row = 0
        for i in range(widget.count()):
            if widget.item(i).data(Qt.UserRole) == att_id:
                row = i
                break
        widget.setCurrentRow(row)

    def _show_image(self, att_id: int | None) -> None:
        self._img_pix = None
        att = self.ctx.files.get(att_id) if att_id else None
        if att is None:
            self.img_view.setText("هنوز تصویری اضافه نشده است.\n"
                                  "تصویر را اینجا بکشید و رها کنید، یا «افزودن تصویر» / «از کلیپ‌بورد» را بزنید.")
            return
        pm = QPixmap(str(self.ctx.files.path_of(att))) if self.ctx.files.exists(att) else QPixmap()
        if pm.isNull():
            self.img_view.setText("این تصویر قابل نمایش نیست.")
            return
        self._img_pix = pm
        self._render_image()

    def _render_image(self) -> None:
        pm = self._img_pix
        if pm is None:
            return
        width = max(120, self.img_scroll.viewport().width() - 16)
        if pm.width() > width:
            pm = pm.scaledToWidth(width, Qt.SmoothTransformation)
        self.img_view.setPixmap(pm)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._render_image()

    def _show_result(self, att_id: int | None) -> None:
        att = self.ctx.files.get(att_id) if att_id else None
        if att is None:
            self.res_view.setPlainText("")
            self.res_view.setPlaceholderText("کد یا فایل نهایی را اضافه کنید یا از کلیپ‌بورد بچسبانید …")
            return
        text = self.ctx.files.read_text(att) if self.ctx.files.exists(att) else None
        self.res_view.setPlainText(text if text is not None else "(این فایل به‌صورت متن قابل نمایش نیست؛ «ذخیره به‌عنوان» را بزنید.)")

    # ---------------------------------------------------------------- افزودن
    def _add_paths(self, paths: list[str], kind: str) -> None:
        last = None
        for f in paths:
            try:
                last = self.ctx.files.add(self._pid(), f, kind=kind)
            except Exception as e:  # noqa: BLE001
                error(self, "افزودن ناموفق", f"{Path(f).name}\n{e}")
        if last is not None:
            if kind == "image":
                self.refresh(select_image=last.id)
            else:
                self.refresh(select_result=last.id)
            self.message.emit("✓ اضافه شد")

    def add_image(self) -> None:
        if not self._ensure():
            return
        files, _ = QFileDialog.getOpenFileNames(self, "انتخاب تصویر", "", IMAGE_FILTER)
        self._add_paths(files, "image")

    def paste_image(self) -> None:
        img = QGuiApplication.clipboard().image()
        if img.isNull():
            info(self, "تصویری در کلیپ‌بورد نیست",
                 "ابتدا از برنامه یا اندیکاتور اسکرین‌شات بگیرید (مثلاً Win+Shift+S) و دوباره امتحان کنید.")
            return
        if not self._ensure():
            return
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        data = bytes(buf.data())
        buf.close()
        try:
            att = self.ctx.files.add_bytes(self._pid(), f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png",
                                           data, kind="image")
        except Exception as e:  # noqa: BLE001
            error(self, "افزودن ناموفق", str(e))
            return
        self.refresh(select_image=att.id)
        self.message.emit("✓ تصویر اضافه شد")

    def add_result_file(self) -> None:
        if not self._ensure():
            return
        files, _ = QFileDialog.getOpenFileNames(self, "انتخاب فایل نهایی", "", "همه‌ی فایل‌ها (*.*)")
        self._add_paths(files, "result")

    def paste_code(self) -> None:
        text = QGuiApplication.clipboard().text()
        if not text.strip():
            info(self, "کلیپ‌بورد خالی است", "ابتدا کد نهایی را از هوش مصنوعی کپی کنید و دوباره امتحان کنید.")
            return
        if not self._ensure():
            return
        name = ask_text(self, "نام فایل", "نام فایل را با پسوند بنویسید (مثلاً indicator.mq5 یا MainActivity.kt):",
                        "result.txt")
        if not name:
            return
        try:
            att = self.ctx.files.add_text(self._pid(), name, text, kind="result")
        except Exception as e:  # noqa: BLE001
            error(self, "افزودن ناموفق", str(e))
            return
        self.refresh(select_result=att.id)
        self.message.emit("✓ کد نهایی ذخیره شد")

    # ---------------------------------------------------------------- عملیات روی انتخاب‌شده‌ها
    def _current(self, widget: QListWidget):
        att_id = self._id_of(widget.currentItem())
        return self.ctx.files.get(att_id) if att_id else None

    def open_image(self) -> None:
        att = self._current(self.img_list)
        if att is not None:
            open_attachment_safely(self.ctx, att, self)

    def remove_image(self) -> None:
        att = self._current(self.img_list)
        if att and confirm(self, "حذف تصویر", f"تصویر «{att.filename}» حذف شود؟", "حذف کن", danger=True):
            self.ctx.files.delete(att.id)
            self.refresh()

    def copy_code(self) -> None:
        att = self._current(self.res_list)
        if att is None:
            info(self, "چیزی انتخاب نشده", "ابتدا یک فایل نتیجه اضافه یا انتخاب کنید.")
            return
        text = self.ctx.files.read_text(att) if self.ctx.files.exists(att) else None
        if text is None:
            info(self, "قابل کپی نیست", "این فایل متنی نیست؛ از «ذخیره به‌عنوان» استفاده کنید.")
            return
        copy_to_clipboard(text)
        self.message.emit("✓ کد کپی شد")

    def save_result_as(self) -> None:
        att = self._current(self.res_list)
        if att is None or not self.ctx.files.exists(att):
            info(self, "چیزی انتخاب نشده", "ابتدا یک فایل نتیجه انتخاب کنید.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "ذخیره‌ی فایل نهایی", att.filename)
        if not dest:
            return
        try:
            shutil.copy2(self.ctx.files.path_of(att), dest)
        except OSError as e:
            error(self, "ذخیره ناموفق", str(e))
            return
        self.message.emit("✓ فایل ذخیره شد")

    def open_result(self) -> None:
        att = self._current(self.res_list)
        if att is not None:
            open_attachment_safely(self.ctx, att, self)

    def remove_result(self) -> None:
        att = self._current(self.res_list)
        if att and confirm(self, "حذف فایل نتیجه", f"«{att.filename}» حذف شود؟", "حذف کن", danger=True):
            self.ctx.files.delete(att.id)
            self.refresh()

    # ---------------------------------------------------------------- کشیدن و رها کردن
    def dragEnterEvent(self, ev) -> None:  # noqa: N802
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:  # noqa: N802
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if not paths or not self._ensure():
            return
        images = [p for p in paths if Path(p).suffix.lower() in IMAGE_EXTENSIONS]
        others = [p for p in paths if p not in images]
        self._add_paths(images, "image")
        self._add_paths(others, "result")
        ev.acceptProposedAction()
