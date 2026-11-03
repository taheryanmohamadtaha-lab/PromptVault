"""صفحه‌ی فهرست پرامپت‌ها: جست‌وجو، فیلتر، مرتب‌سازی، پیش‌نمایش و عملیات (کپی، علاقه‌مندی، بایگانی، حذف ...).

یک کلاس برای همه‌ی حالت‌ها: all | favorites | recent | archived | trash
"""
from __future__ import annotations

from PySide6.QtCore import QDate, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..core.context import AppContext
from ..models.prompt import IMPORTANCE_LABELS
from ..services.search_service import PromptFilter
from .dialogs import (
    CompareDialog, MoveDialog, confirm, copy_to_clipboard, error, fill_category_combo, select_combo_data,
)
from .widgets import ROLE_PROMPT_ID, PromptDelegate, prompt_item_data

MODE_TITLES = {
    "all": "همه‌ی پرامپت‌ها",
    "favorites": "علاقه‌مندی‌ها",
    "recent": "اخیراً استفاده‌شده",
    "archived": "بایگانی",
    "trash": "سطل بازیافت",
}
MODE_EMPTY = {
    "all": "هنوز پرامپتی ثبت نشده است. با دکمه‌ی «پرامپت جدید» شروع کنید.",
    "favorites": "هنوز پرامپتی را به علاقه‌مندی‌ها اضافه نکرده‌اید. روی هر پرامپت راست‌کلیک و «علاقه‌مندی» را بزنید.",
    "recent": "هنوز پرامپتی کپی یا استفاده نشده است.",
    "archived": "بایگانی خالی است.",
    "trash": "سطل بازیافت خالی است.",
}
SORT_CHOICES = [
    ("updated", "آخرین ویرایش"), ("created", "تاریخ ایجاد"), ("title", "عنوان (الفبایی)"),
    ("used", "آخرین استفاده"), ("use_count", "بیشترین استفاده"), ("importance", "میزان اهمیت"),
]


class DateRange(QWidget):
    """دو انتخاب‌گر تاریخ «از ... تا ...» که فقط وقتی تیک می‌خورند اعمال می‌شوند."""
    changed = Signal()

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(label))
        self.from_cb = QCheckBox("از")
        self.from_ed = QDateEdit(QDate.currentDate().addMonths(-1))
        self.to_cb = QCheckBox("تا")
        self.to_ed = QDateEdit(QDate.currentDate())
        for ed in (self.from_ed, self.to_ed):
            ed.setCalendarPopup(True)
            ed.setDisplayFormat("yyyy-MM-dd")
            ed.setEnabled(False)
            ed.dateChanged.connect(lambda _d: self.changed.emit())
        self.from_cb.toggled.connect(self._toggle)
        self.to_cb.toggled.connect(self._toggle)
        for w in (self.from_cb, self.from_ed, self.to_cb, self.to_ed):
            lay.addWidget(w)
        lay.addStretch(1)

    def _toggle(self, _on: bool) -> None:
        self.from_ed.setEnabled(self.from_cb.isChecked())
        self.to_ed.setEnabled(self.to_cb.isChecked())
        self.changed.emit()

    def values(self) -> tuple[str, str]:
        a = self.from_ed.date().toString("yyyy-MM-dd") if self.from_cb.isChecked() else ""
        b = self.to_ed.date().toString("yyyy-MM-dd") if self.to_cb.isChecked() else ""
        return a, b

    def reset(self) -> None:
        self.from_cb.setChecked(False)
        self.to_cb.setChecked(False)


class PromptListPage(QWidget):
    open_prompt = Signal(int)
    new_prompt = Signal()
    changed = Signal()          # داده تغییر کرد (برای تازه‌سازی صفحه‌های دیگر)
    message = Signal(str)       # پیام کوتاه (Toast)

    def __init__(self, ctx: AppContext, mode: str = "all", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        self.mode = mode
        self._results: list = []
        # تایمر باید پیش از ساخت رابط وجود داشته باشد، چون سیگنال‌های فیلتر هنگام ساخت از آن استفاده می‌کنند
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._run)
        self._build()

    # ---------------------------------------------------------------- ساخت رابط
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        self.title = QLabel(MODE_TITLES[self.mode])
        self.title.setObjectName("h1")
        self.count = QLabel("")
        self.count.setObjectName("muted")
        head.addWidget(self.title)
        head.addWidget(self.count)
        head.addStretch(1)
        if self.mode in ("all", "favorites", "recent"):
            self.new_btn = QPushButton("➕ پرامپت جدید")
            self.new_btn.setObjectName("primary")
            self.new_btn.clicked.connect(self.new_prompt.emit)
            head.addWidget(self.new_btn)
        if self.mode == "trash":
            self.empty_btn = QPushButton("🗑️ خالی کردن سطل")
            self.empty_btn.setObjectName("danger")
            self.empty_btn.clicked.connect(self._empty_trash)
            head.addWidget(self.empty_btn)
        root.addLayout(head)

        # ---- ردیف جست‌وجو
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("جست‌وجو در عنوان، متن، توضیحات، دسته‌بندی، برچسب و پلتفرم …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._timer.start())
        self.adv_btn = QPushButton("فیلتر پیشرفته ▾")
        self.adv_btn.setCheckable(True)
        self.adv_btn.toggled.connect(self._toggle_advanced)
        self.reset_btn = QPushButton("پاک کردن فیلترها")
        self.reset_btn.clicked.connect(self.reset_filters)
        row.addWidget(self.search, 1)
        row.addWidget(self.adv_btn)
        row.addWidget(self.reset_btn)
        root.addLayout(row)

        # ---- فیلترها
        frow = QHBoxLayout()
        self.category = QComboBox()
        self.platform = QComboBox()
        self.tag = QComboBox()
        self.importance = QComboBox()
        for text, val in (("همه‌ی سطوح اهمیت", 0), ("متوسط و بالاتر", 2), ("زیاد و بالاتر", 3), ("فقط حیاتی", 4)):
            self.importance.addItem(text, val)
        self.usage = QComboBox()
        self.usage.addItem("استفاده‌شده و نشده", None)
        self.usage.addItem("فقط استفاده‌شده‌ها", True)
        self.usage.addItem("فقط استفاده‌نشده‌ها", False)
        self.sort = QComboBox()
        for key, text in SORT_CHOICES:
            self.sort.addItem("مرتب‌سازی: " + text, key)
        if self.mode == "recent":
            select_combo_data(self.sort, "used")
        for w in (self.category, self.platform, self.tag, self.importance, self.usage, self.sort):
            w.currentIndexChanged.connect(lambda _i: self._timer.start())
            frow.addWidget(w, 1)
        if self.mode == "recent":
            self.usage.setCurrentIndex(1)
            self.usage.setEnabled(False)
        root.addLayout(frow)

        # ---- فیلتر پیشرفته (تاریخ)
        self.adv = QFrame()
        self.adv.setObjectName("panel")
        al = QVBoxLayout(self.adv)
        self.created_range = DateRange("تاریخ ایجاد:")
        self.updated_range = DateRange("تاریخ ویرایش:")
        for r in (self.created_range, self.updated_range):
            r.changed.connect(self._timer.start)
            al.addWidget(r)
        self.adv.hide()
        root.addWidget(self.adv)

        # ---- فهرست + پیش‌نمایش
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.setUniformItemSizes(False)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.delegate = PromptDelegate(self.list)
        self.delegate.show_preview = bool(self.ctx.settings.get("list_show_preview"))
        self.list.setItemDelegate(self.delegate)
        self.list.itemDoubleClicked.connect(lambda it: self.open_prompt.emit(it.data(ROLE_PROMPT_ID)))
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemSelectionChanged.connect(self._selection_changed)
        split.addWidget(self.list)

        self.side = QFrame()
        self.side.setObjectName("panel")
        sl = QVBoxLayout(self.side)
        self.p_title = QLabel("")
        self.p_title.setObjectName("h2")
        self.p_title.setWordWrap(True)
        self.p_meta = QLabel("")
        self.p_meta.setObjectName("muted")
        self.p_meta.setWordWrap(True)
        self.p_img = QLabel("")
        self.p_img.setAlignment(Qt.AlignCenter)
        self.p_img.setCursor(Qt.PointingHandCursor)
        self.p_img.setToolTip("برای دیدن تصویر در اندازه‌ی کامل، پرامپت را ویرایش کنید و تب «تصویر و نتیجه» را باز کنید")
        self.p_img.hide()
        self.p_body = QPlainTextEdit()
        self.p_body.setReadOnly(True)
        self.p_result = QPushButton("📄 کپی کد / نتیجه‌ی نهایی")
        self.p_result.clicked.connect(self._copy_result)
        self.p_result.hide()
        brow = QHBoxLayout()
        self.p_copy = QPushButton("📋 کپی پرامپت")
        self.p_copy.setObjectName("primary")
        self.p_copy.clicked.connect(self._copy_current)
        self.p_edit = QPushButton("✏️ ویرایش")
        self.p_edit.clicked.connect(self._edit_current)
        brow.addWidget(self.p_copy)
        brow.addWidget(self.p_edit)
        sl.addWidget(self.p_title)
        sl.addWidget(self.p_meta)
        sl.addWidget(self.p_img)
        sl.addWidget(self.p_body, 1)
        sl.addWidget(self.p_result)
        sl.addLayout(brow)
        self.sim_label = QLabel("پرامپت‌های مشابه:")
        self.sim_label.setObjectName("muted")
        self.sim_list = QListWidget()
        self.sim_list.setMaximumHeight(120)
        self.sim_list.itemDoubleClicked.connect(lambda it: self.open_prompt.emit(it.data(ROLE_PROMPT_ID)))
        sl.addWidget(self.sim_label)
        sl.addWidget(self.sim_list)
        split.addWidget(self.side)
        split.setSizes([620, 380])
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)

        self.empty = QLabel("")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        root.addWidget(self.empty)

        # ---- میانبرها (فقط وقتی فهرست فوکوس دارد، تا با تایپ در کادر جست‌وجو تداخل نکنند)
        for seq, fn in (("Ctrl+C", self._copy_current), ("Ctrl+E", self._edit_current),
                        ("Ctrl+D", self._duplicate_selected), ("Delete", self._delete_selected),
                        ("Return", self._edit_current)):
            QShortcut(QKeySequence(seq), self.list, activated=fn, context=Qt.WidgetShortcut)

        self._reload_filters()

    # ---------------------------------------------------------------- فیلترها
    def _reload_filters(self) -> None:
        """گزینه‌های دسته‌بندی/پلتفرم/برچسب را از دیتابیس تازه می‌کند و انتخاب فعلی را نگه می‌دارد."""
        # توجه: مقدار None برای دسته‌بندی یعنی «بدون دسته‌بندی»؛ کمبوی خالی باید به «همه» برگردد.
        cur_cat = self.category.currentData() if self.category.count() else "__all__"
        cur_plat, cur_tag = self.platform.currentData(), self.tag.currentData()
        for w in (self.category, self.platform, self.tag):
            w.blockSignals(True)
        fill_category_combo(self.category, self.ctx, include_none="بدون دسته‌بندی", include_all="همه‌ی دسته‌ها")
        select_combo_data(self.category, cur_cat)  # اگر دیگر وجود نداشت، روی «همه» می‌ماند
        self.platform.clear()
        self.platform.addItem("همه‌ی پلتفرم‌ها", "")
        for p in self.ctx.search.platforms():
            self.platform.addItem(p, p)
        select_combo_data(self.platform, cur_plat or "")
        self.tag.clear()
        self.tag.addItem("همه‌ی برچسب‌ها", "")
        for t in self.ctx.tags.all():
            if t.count:
                self.tag.addItem(f"#{t.name} ({t.count})", t.name)
        select_combo_data(self.tag, cur_tag or "")
        for w in (self.category, self.platform, self.tag):
            w.blockSignals(False)

    def _toggle_advanced(self, on: bool) -> None:
        self.adv.setVisible(on)
        self.adv_btn.setText("فیلتر پیشرفته ▴" if on else "فیلتر پیشرفته ▾")

    def reset_filters(self) -> None:
        for w in (self.search, self.category, self.platform, self.tag, self.importance, self.usage, self.sort):
            w.blockSignals(True)
        self.search.clear()
        select_combo_data(self.category, "__all__")
        self.platform.setCurrentIndex(0)
        self.tag.setCurrentIndex(0)
        self.importance.setCurrentIndex(0)
        self.usage.setCurrentIndex(1 if self.mode == "recent" else 0)
        select_combo_data(self.sort, "used" if self.mode == "recent" else "updated")
        for w in (self.search, self.category, self.platform, self.tag, self.importance, self.usage, self.sort):
            w.blockSignals(False)
        self.created_range.reset()
        self.updated_range.reset()
        self._run()

    def current_filter(self) -> PromptFilter:
        f = PromptFilter(query=self.search.text().strip(), sort=self.sort.currentData() or "updated")
        f.view = {"archived": "archived", "trash": "trash"}.get(self.mode, "active")
        if self.mode == "favorites":
            f.favorite_only = True
        cat = self.category.currentData()
        if cat is None:
            f.uncategorized = True
        elif cat != "__all__":
            f.category_id = cat
        f.platform = self.platform.currentData() or ""
        f.tag = self.tag.currentData() or ""
        f.min_importance = self.importance.currentData() or 0
        f.used = self.usage.currentData()
        f.created_from, f.created_to = self.created_range.values()
        f.updated_from, f.updated_to = self.updated_range.values()
        return f

    # ---------------------------------------------------------------- نمایش
    def refresh(self) -> None:
        self.delegate.show_preview = bool(self.ctx.settings.get("list_show_preview"))
        self._reload_filters()
        self._run()

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def set_query(self, text: str) -> None:
        self.search.setText(text)  # _timer اجرا می‌شود؛ ولی فوراً هم اجرا کنیم
        self._run()

    def set_category(self, category_id: int | None) -> None:
        self._reload_filters()
        select_combo_data(self.category, category_id if category_id is not None else "__all__")
        self._run()

    def set_tag(self, name: str) -> None:
        self._reload_filters()
        select_combo_data(self.tag, name)
        self._run()

    def _category_names(self) -> dict[int, str]:
        flat = {c.id: c for c in self.ctx.categories.flat()}
        names: dict[int, str] = {}
        for cid in flat:
            parts, cur, guard = [], cid, 0
            while cur is not None and guard < 20:
                c = flat.get(cur)
                if c is None:
                    break
                parts.append(c.name)
                cur = c.parent_id
                guard += 1
            names[cid] = " ‹ ".join(reversed(parts))
        return names

    def _run(self) -> None:
        keep = self.selected_ids()
        f = self.current_filter()
        self._results = self.ctx.search.search(f)
        names = self._category_names()
        self.delegate.query = f.query
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        for p in self._results:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, prompt_item_data(p, names.get(p.category_id, "")))
            it.setData(ROLE_PROMPT_ID, p.id)
            self.list.addItem(it)
            if p.id in keep:
                it.setSelected(True)
        self.list.setUpdatesEnabled(True)
        self.count.setText(f"({len(self._results)} مورد)")
        filtering = bool(f.query or f.category_id is not None or f.uncategorized or f.tag or f.platform
                         or f.min_importance or f.used is not None and self.mode != "recent"
                         or f.created_from or f.created_to or f.updated_from or f.updated_to)
        if not self._results:
            self.empty.setText("نتیجه‌ای برای این جست‌وجو/فیلتر پیدا نشد." if filtering else MODE_EMPTY[self.mode])
        self.empty.setVisible(not self._results)
        self._selection_changed()

    # ---------------------------------------------------------------- انتخاب‌ها
    def selected_ids(self) -> list[int]:
        return [it.data(ROLE_PROMPT_ID) for it in self.list.selectedItems()]

    def _current_id(self) -> int | None:
        ids = self.selected_ids()
        if ids:
            return ids[0]
        it = self.list.currentItem()
        return it.data(ROLE_PROMPT_ID) if it else None

    def _selection_changed(self) -> None:
        pid = self.selected_ids()[0] if self.selected_ids() else None
        has = pid is not None
        for w in (self.p_copy, self.p_edit):
            w.setEnabled(has)
        self.sim_list.clear()
        self._show_result_preview(pid)
        if not has:
            self.p_title.setText("")
            self.p_meta.setText("")
            self.p_body.setPlainText("")
            self.sim_label.hide()
            self.sim_list.hide()
            return
        p = self.ctx.prompts.get(pid)
        if p is None:
            return
        self.p_title.setText(p.title)
        meta = [self.ctx.categories.path_name(p.category_id) or "بدون دسته‌بندی"]
        if p.platform:
            meta.append(p.platform)
        if p.output_type:
            meta.append("خروجی: " + p.output_type)
        meta.append("وضعیت: " + p.status)
        meta.append("اهمیت: " + IMPORTANCE_LABELS.get(p.importance, ""))
        if p.tags:
            meta.append(" ".join("#" + t for t in p.tags))
        meta.append(f"ویرایش: {p.updated_at.replace('T', ' ')}")
        if p.use_count:
            meta.append(f"{p.use_count} بار استفاده")
        self.p_meta.setText(" • ".join(meta))
        self.p_body.setPlainText(p.body)
        similar = self.ctx.prompts.similar(pid) if self.mode != "trash" else []
        for s in similar:
            it = QListWidgetItem(s.title)
            it.setData(ROLE_PROMPT_ID, s.id)
            self.sim_list.addItem(it)
        self.sim_label.setVisible(bool(similar))
        self.sim_list.setVisible(bool(similar))
        trash = self.mode == "trash"
        self.p_copy.setEnabled(not trash)
        self.p_edit.setEnabled(not trash)

    def _show_result_preview(self, pid: int | None) -> None:
        """تصویر نتیجه (اولین تصویر) کنار پرامپت + دکمه‌ی کپی کد نهایی."""
        self.p_img.hide()
        self.p_img.clear()
        self.p_result.hide()
        if pid is None:
            return
        files = self.ctx.files
        for a in files.list(pid, "image"):
            pm = QPixmap(str(files.path_of(a))) if files.exists(a) else QPixmap()
            if not pm.isNull():
                self.p_img.setPixmap(pm.scaled(QSize(380, 210), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.p_img.show()
                break
        results = files.list(pid, "result")
        if results:
            self.p_result.setText("📄 کپی کد / نتیجه‌ی نهایی" + (f" ({len(results)} فایل)" if len(results) > 1 else ""))
            self.p_result.show()

    def _copy_result(self) -> None:
        pid = self._current_id()
        if pid is None:
            return
        results = [a for a in self.ctx.files.list(pid, "result") if self.ctx.files.exists(a)]
        if not results:
            return
        if len(results) == 1:
            self._copy_result_file(results[0])
            return
        from PySide6.QtGui import QCursor
        menu = QMenu(self)
        for a in results:
            menu.addAction(a.filename, lambda a=a: self._copy_result_file(a))
        menu.exec(QCursor.pos())

    def _copy_result_file(self, att) -> None:
        text = self.ctx.files.read_text(att)
        if text is None:
            error(self, "قابل کپی نیست", "این فایل متنی نیست؛ از ویرایشگر، تب «تصویر و نتیجه» و «ذخیره به‌عنوان» استفاده کنید.")
            return
        copy_to_clipboard(text)
        self.message.emit(f"«{att.filename}» کپی شد")

    # ---------------------------------------------------------------- عملیات
    def _copy_current(self) -> None:
        pid = self._current_id()
        if pid is None:
            return
        p = self.ctx.prompts.get(pid)
        if p is None:
            return
        copy_to_clipboard(p.body)
        self.ctx.prompts.mark_used(pid)
        self.message.emit("پرامپت کپی شد")
        self.changed.emit()

    def _edit_current(self) -> None:
        pid = self._current_id()
        if pid is not None and self.mode != "trash":
            self.open_prompt.emit(pid)

    def _duplicate_selected(self) -> None:
        ids = self.selected_ids()
        if not ids or self.mode == "trash":
            return
        for pid in ids:
            self.ctx.prompts.duplicate(pid)
        self.message.emit("نسخه‌ی کپی ساخته شد" if len(ids) == 1 else f"{len(ids)} نسخه‌ی کپی ساخته شد")
        self.changed.emit()
        self.refresh()

    def _toggle_flag(self, flag: str) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        prompts = [self.ctx.prompts.get(i) for i in ids]
        new_value = not all(getattr(p, flag) for p in prompts if p)
        setter = {"favorite": self.ctx.prompts.set_favorite, "pinned": self.ctx.prompts.set_pinned,
                  "archived": self.ctx.prompts.set_archived}[flag]
        for pid in ids:
            setter(pid, new_value)
        self.changed.emit()
        self.refresh()

    def _move_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        dlg = MoveDialog(self.ctx, self)
        if dlg.exec():
            try:
                self.ctx.prompts.move(ids, dlg.category_id())
            except (KeyError, ValueError) as e:
                error(self, "انتقال ممکن نشد", str(e))
                return
            self.message.emit("پرامپت‌ها منتقل شدند")
            self.changed.emit()
            self.refresh()

    def _compare(self) -> None:
        pid = self._current_id()
        if pid is not None:
            CompareDialog(self.ctx, pid, self).exec()

    def _delete_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        if self.mode == "trash":
            if not confirm(self, "حذف دائمی",
                           f"{len(ids)} پرامپت برای همیشه حذف می‌شود (همراه با تاریخچه و پیوست‌ها). "
                           "این کار قابل بازگشت نیست.", "حذف دائمی", danger=True):
                return
            self.ctx.prompts.purge(ids, self.ctx.files)
        else:
            self.ctx.prompts.trash(ids)
            self.message.emit("به سطل بازیافت منتقل شد (قابل بازیابی است)")
        self.changed.emit()
        self.refresh()

    def _restore_selected(self) -> None:
        ids = self.selected_ids()
        if ids:
            self.ctx.prompts.restore(ids)
            self.message.emit("پرامپت بازیابی شد")
            self.changed.emit()
            self.refresh()

    def _empty_trash(self) -> None:
        n = self.ctx.prompts.stats()["trash"]
        if not n:
            return
        if confirm(self, "خالی کردن سطل بازیافت",
                   f"همه‌ی {n} پرامپت داخل سطل برای همیشه حذف می‌شوند. این کار قابل بازگشت نیست.",
                   "حذف دائمی همه", danger=True):
            self.ctx.prompts.empty_trash(self.ctx.files)
            self.changed.emit()
            self.refresh()

    def _context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        if not item.isSelected():
            self.list.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        if self.mode == "trash":
            menu.addAction("♻️ بازیابی", self._restore_selected)
            menu.addAction("❌ حذف دائمی", self._delete_selected)
        else:
            menu.addAction("✏️ ویرایش\tCtrl+E", self._edit_current)
            menu.addAction("📋 کپی پرامپت\tCtrl+C", self._copy_current)
            menu.addSeparator()
            menu.addAction("⭐ علاقه‌مندی (روشن/خاموش)", lambda: self._toggle_flag("favorite"))
            menu.addAction("📌 سنجاق (روشن/خاموش)", lambda: self._toggle_flag("pinned"))
            menu.addAction("🗂️ انتقال به دسته‌بندی …", self._move_selected)
            menu.addAction("⧉ تکثیر\tCtrl+D", self._duplicate_selected)
            menu.addAction("⇄ مقایسه با پرامپت دیگر …", self._compare)
            menu.addSeparator()
            menu.addAction("📦 بایگانی / خروج از بایگانی", lambda: self._toggle_flag("archived"))
            menu.addAction("🗑️ حذف (انتقال به سطل)\tDel", self._delete_selected)
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self.list.scheduleDelayedItemsLayout()
