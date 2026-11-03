"""داشبورد: آمار کلیدی، جست‌وجوی سریع، دکمه‌ی افزودن پرامپت و فهرست‌های اخیر/مهم."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME_FA, APP_SLOGAN
from ..core.context import AppContext
from ..services.search_service import PromptFilter
from .widgets import ROLE_PROMPT_ID, StatCard, add_shadow, prompt_tooltip


class _Section(QFrame):
    """کادر یک فهرست کوتاه (مثلاً «آخرین پرامپت‌های اضافه‌شده»)."""
    open_prompt = Signal(int)

    def __init__(self, ctx: AppContext, title: str, empty_text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("panel")
        self._empty_text = empty_text
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        head = QLabel(title)
        head.setObjectName("h2")
        lay.addWidget(head)
        self.list = QListWidget()
        self.list.setMinimumHeight(190)
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.itemClicked.connect(lambda it: self._clicked(it))
        lay.addWidget(self.list)
        add_shadow(self, blur=18, dy=3, alpha=28)

    def _clicked(self, item: QListWidgetItem) -> None:
        pid = item.data(ROLE_PROMPT_ID)
        if pid:
            self.open_prompt.emit(pid)

    def fill(self, prompts) -> None:
        self.list.clear()
        if not prompts:
            it = QListWidgetItem(self._empty_text)
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)
            return
        for p in prompts:
            badge = ("📌 " if p.pinned else "") + ("⭐ " if p.favorite else "")
            it = QListWidgetItem(f"{badge}{p.title}")
            it.setData(ROLE_PROMPT_ID, p.id)
            it.setToolTip(prompt_tooltip(self.ctx, p))
            self.list.addItem(it)


class DashboardPage(QWidget):
    open_prompt = Signal(int)
    new_prompt = Signal()
    navigate = Signal(str)          # نام صفحه‌ی مقصد
    search_requested = Signal(str)  # متن جست‌وجو → صفحه‌ی «همه‌ی پرامپت‌ها»

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
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        # ---- سربرگ
        head = QHBoxLayout()
        titles = QVBoxLayout()
        h = QLabel(f"{APP_NAME_FA}")
        h.setObjectName("h1")
        s = QLabel(APP_SLOGAN)
        s.setObjectName("slogan")
        titles.addWidget(h)
        titles.addWidget(s)
        head.addLayout(titles, 1)
        self.big_btn = QPushButton("➕  افزودن پرامپت جدید")
        self.big_btn.setObjectName("big")
        self.big_btn.setCursor(Qt.PointingHandCursor)
        self.big_btn.clicked.connect(self.new_prompt.emit)
        add_shadow(self.big_btn, blur=22, dy=5, alpha=60)
        head.addWidget(self.big_btn)
        root.addLayout(head)

        # ---- جست‌وجوی سریع
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("🔍  جست‌وجوی سریع در همه‌ی پرامپت‌ها … (برای دیدن نتایج Enter بزنید)")
        self.search.returnPressed.connect(self._do_search)
        root.addWidget(self.search)

        # ---- کارت‌های آماری
        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {
            "total": StatCard("📚", "کل پرامپت‌ها"),
            "categories": StatCard("🗂️", "دسته‌بندی‌ها"),
            "favorites": StatCard("⭐", "علاقه‌مندی‌ها"),
            "recent_used": StatCard("🕘", "اخیراً استفاده‌شده"),
        }
        targets = {"total": "all", "categories": "categories", "favorites": "favorites", "recent_used": "recent"}
        for i, (key, card) in enumerate(self.cards.items()):
            card.clicked.connect(lambda t=targets[key]: self.navigate.emit(t))
            grid.addWidget(card, 0, i)
            grid.setColumnStretch(i, 1)
        root.addLayout(grid)

        # ---- فهرست‌ها
        lists = QGridLayout()
        lists.setSpacing(14)
        self.sec_added = _Section(ctx, "🆕 آخرین پرامپت‌های اضافه‌شده", "هنوز پرامپتی اضافه نشده است.")
        self.sec_edited = _Section(ctx, "✏️ آخرین پرامپت‌های ویرایش‌شده", "هنوز ویرایشی انجام نشده است.")
        self.sec_important = _Section(ctx, "⭐ پرامپت‌های مهم و ستاره‌دار", "پرامپتی با علاقه‌مندی، سنجاق یا اهمیت زیاد نیست.")
        self.sec_used = _Section(ctx, "🕘 اخیراً استفاده‌شده", "هنوز پرامپتی کپی نشده است.")
        for sec in (self.sec_added, self.sec_edited, self.sec_important, self.sec_used):
            sec.open_prompt.connect(self.open_prompt.emit)
        lists.addWidget(self.sec_added, 0, 0)
        lists.addWidget(self.sec_edited, 0, 1)
        lists.addWidget(self.sec_important, 1, 0)
        lists.addWidget(self.sec_used, 1, 1)
        lists.setColumnStretch(0, 1)
        lists.setColumnStretch(1, 1)
        root.addLayout(lists)
        root.addStretch(1)

    def _do_search(self) -> None:
        text = self.search.text().strip()
        if text:
            self.search_requested.emit(text)
            self.search.clear()

    def focus_search(self) -> None:
        self.search.setFocus()

    def refresh(self) -> None:
        st = self.ctx.prompts.stats()
        self.cards["total"].set_value(st["total"])
        self.cards["categories"].set_value(st["categories"])
        self.cards["favorites"].set_value(st["favorites"])
        self.cards["recent_used"].set_value(st["recent_used"])
        s = self.ctx.search
        self.sec_added.fill(s.recent_added(6))
        self.sec_edited.fill(s.recent_edited(6))
        merged, seen = [], set()
        for p in s.search(PromptFilter(favorite_only=True, limit=6)) + s.important(6):
            if p.id not in seen:
                seen.add(p.id)
                merged.append(p)
        self.sec_important.fill(merged[:6])
        self.sec_used.fill(s.recent_used(6))
