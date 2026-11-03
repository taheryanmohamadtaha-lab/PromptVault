"""پنجره‌ی جست‌وجوی سریع (Ctrl+K در برنامه، یا میانبر سراسری در ویندوز):
تایپ کنید، با ↑↓ انتخاب کنید، Enter = کپی متن پرامپت، Ctrl+Enter = باز کردن برای ویرایش."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from ..core.context import AppContext
from ..services.search_service import PromptFilter
from .dialogs import copy_to_clipboard
from .widgets import ROLE_PROMPT_ID, prompt_tooltip


class QuickSearchDialog(QDialog):
    HINT = "Enter: کپی پرامپت  •  Ctrl+Enter: باز کردن برای ویرایش  •  Esc: بستن"
    open_requested = Signal(int)
    copied = Signal(str)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("جست‌وجوی سریع پرامپت")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        self.input = QLineEdit()
        self.input.setObjectName("search")
        self.input.setPlaceholderText("عنوان یا بخشی از متن پرامپت را بنویسید …")
        self.input.textChanged.connect(lambda _t: self._timer.start())
        lay.addWidget(self.input)
        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _it: self._copy_current())
        self.list.itemDoubleClicked.connect(lambda _it: self._copy_current())
        lay.addWidget(self.list, 1)
        self.hint = QLabel(self.HINT)
        self.hint.setObjectName("muted")
        lay.addWidget(self.hint)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._search)
        QShortcut(QKeySequence("Down"), self.input, activated=lambda: self._move(1), context=Qt.WidgetShortcut)
        QShortcut(QKeySequence("Up"), self.input, activated=lambda: self._move(-1), context=Qt.WidgetShortcut)
        self.input.returnPressed.connect(self._copy_current)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._open_current)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._open_current)

    def popup(self) -> None:
        self.hint.setText(self.HINT)
        self.input.clear()
        self._search()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def _search(self) -> None:
        text = self.input.text().strip()
        if text:
            results = self.ctx.search.search(PromptFilter(query=text, sort="use_count", limit=50))
        else:
            results = self.ctx.search.search(PromptFilter(sort="used", limit=25))
        self.list.clear()
        for p in results:
            it = QListWidgetItem(("⭐ " if p.favorite else "") + p.title)
            it.setData(ROLE_PROMPT_ID, p.id)
            it.setToolTip(prompt_tooltip(self.ctx, p))
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _move(self, step: int) -> None:
        n = self.list.count()
        if n:
            self.list.setCurrentRow(max(0, min(n - 1, self.list.currentRow() + step)))

    def _current_id(self) -> int | None:
        it = self.list.currentItem()
        return it.data(ROLE_PROMPT_ID) if it else None

    def _copy_current(self) -> None:
        pid = self._current_id()
        p = self.ctx.prompts.get(pid) if pid else None
        if p is None:
            return
        copy_to_clipboard(p.body)
        self.ctx.prompts.mark_used(pid)
        self.hint.setText("✅ پرامپت کپی شد")
        self.copied.emit(p.title)
        QTimer.singleShot(500, self.close)

    def _open_current(self) -> None:
        pid = self._current_id()
        if pid:
            self.open_requested.emit(pid)
            self.close()
