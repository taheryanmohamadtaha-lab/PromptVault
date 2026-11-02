"""مدیریت دسته‌بندی‌های درختی و برچسب‌ها."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QRadioButton, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from ..core.context import AppContext
from .dialogs import MoveDialog, ask_text, confirm, error, fill_category_combo
from .widgets import ROLE_PROMPT_ID

ICON_CHOICES = ["📁", "🎨", "🎬", "🤖", "🍎", "🎮", "🪟", "📈", "📊", "📉", "⚙️", "🧠", "🌐", "🧩", "✍️", "📦",
                "💡", "🔧", "📱", "💻", "🛒", "📚", "🎵", "📷", "🚀", "🔥", "🧪", "🗂️"]
ROLE_CAT_ID = Qt.UserRole + 2


def _color_icon(color: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(QColor(color))
    return QIcon(pm)


class CategoryDialog(QDialog):
    """ساخت/ویرایش دسته: نام، آیکون و رنگ."""

    def __init__(self, parent: QWidget | None, title: str, name: str = "", icon: str = "📁",
                 color: str = "#6C63FF", ask_name: bool = True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._color = color
        form = QFormLayout(self)
        self.name = QLineEdit(name)
        self.name.setEnabled(ask_name)
        self.icon = QComboBox()
        self.icon.setEditable(True)
        self.icon.addItems(ICON_CHOICES)
        self.icon.setCurrentText(icon)
        self.color_btn = QPushButton("انتخاب رنگ …")
        self.color_btn.clicked.connect(self._pick)
        self._paint_btn()
        form.addRow("نام دسته‌بندی:", self.name)
        form.addRow("آیکون:", self.icon)
        form.addRow("رنگ:", self.color_btn)
        bb = QDialogButtonBox()
        ok = bb.addButton("ذخیره", QDialogButtonBox.AcceptRole)
        ok.setObjectName("primary")
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "رنگ دسته‌بندی")
        if c.isValid():
            self._color = c.name().upper()
            self._paint_btn()

    def _paint_btn(self) -> None:
        self.color_btn.setIcon(_color_icon(self._color))
        self.color_btn.setText(f"  {self._color}")

    def _accept(self) -> None:
        if self.name.isEnabled() and not self.name.text().strip():
            error(self, "نام لازم است", "نام دسته‌بندی را وارد کنید.")
            return
        self.accept()

    def values(self) -> tuple[str, str, str]:
        return self.name.text().strip(), (self.icon.currentText().strip() or "📁"), self._color


class DeleteCategoryDialog(QDialog):
    """پرسیدن تکلیف پرامپت‌های داخل دسته‌ای که حذف می‌شود."""

    def __init__(self, ctx: AppContext, category_id: int, parent: QWidget | None = None):
        super().__init__(parent)
        cat = ctx.categories.get(category_id)
        self.setWindowTitle("حذف دسته‌بندی")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"دسته‌بندی «{cat.name}» حذف می‌شود. زیردسته‌های آن به سطح بالاتر منتقل می‌شوند.\n"
                             "با پرامپت‌های داخل این دسته (در خود همین دسته) چه کنیم؟"))
        self.r_none = QRadioButton("بدون دسته‌بندی شوند (پیشنهادی)")
        self.r_move = QRadioButton("به این دسته‌بندی منتقل شوند:")
        self.r_trash = QRadioButton("به سطل بازیافت بروند (قابل بازیابی)")
        self.r_none.setChecked(True)
        self.target = QComboBox()
        fill_category_combo(self.target, ctx, include_none="")
        # دسته‌ی در حال حذف را از مقصدها خارج کن
        for i in range(self.target.count() - 1, -1, -1):
            if self.target.itemData(i) == category_id:
                self.target.removeItem(i)
        self.target.setEnabled(False)
        self.r_move.toggled.connect(self.target.setEnabled)
        if self.target.count() == 0:
            self.r_move.setEnabled(False)
        for w in (self.r_none, self.r_move, self.target, self.r_trash):
            lay.addWidget(w)
        bb = QDialogButtonBox()
        ok = bb.addButton("حذف دسته‌بندی", QDialogButtonBox.AcceptRole)
        ok.setObjectName("danger")
        bb.addButton("انصراف", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def choice(self) -> tuple[str, int | None]:
        if self.r_move.isChecked():
            return "move", self.target.currentData()
        if self.r_trash.isChecked():
            return "trash", None
        return "uncategorize", None


class CategoriesPage(QWidget):
    changed = Signal()
    message = Signal(str)
    show_category = Signal(int)     # باز کردن فهرست پرامپت‌های یک دسته
    show_tag = Signal(str)          # باز کردن فهرست پرامپت‌های یک برچسب
    open_prompt = Signal(int)
    new_prompt_in = Signal(int)     # پرامپت جدید داخل دسته‌ی انتخاب‌شده

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 14)
        title = QLabel("دسته‌بندی‌ها و برچسب‌ها")
        title.setObjectName("h1")
        root.addWidget(title)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_categories(), "🗂️ دسته‌بندی‌ها")
        self.tabs.addTab(self._build_tags(), "🏷️ برچسب‌ها")

    # ---------------------------------------------------------------- دسته‌بندی‌ها
    def _build_categories(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._cat_selected)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self.show_category.emit(it.data(0, ROLE_CAT_ID)))
        left.addWidget(self.tree, 1)
        lay.addLayout(left, 3)

        side = QFrame()
        side.setObjectName("panel")
        sl = QVBoxLayout(side)
        self.cat_title = QLabel("یک دسته‌بندی را انتخاب کنید")
        self.cat_title.setObjectName("h2")
        sl.addWidget(self.cat_title)
        self.btn_new = QPushButton("➕ دسته‌بندی جدید (سطح اصلی)")
        self.btn_sub = QPushButton("↳ زیردسته‌ی جدید")
        self.btn_rename = QPushButton("✏️ تغییر نام")
        self.btn_style = QPushButton("🎨 آیکون و رنگ")
        self.btn_move = QPushButton("⇅ انتقال این دسته به دسته‌ی دیگر")
        self.btn_delete = QPushButton("🗑️ حذف دسته‌بندی")
        self.btn_delete.setObjectName("danger")
        self.btn_show = QPushButton("📚 نمایش پرامپت‌های این دسته")
        self.btn_add_prompt = QPushButton("＋ پرامپت جدید در این دسته")
        self.btn_new.clicked.connect(lambda: self._add(None))
        self.btn_sub.clicked.connect(lambda: self._add(self._sel_id()))
        self.btn_rename.clicked.connect(self._rename)
        self.btn_style.clicked.connect(self._style)
        self.btn_move.clicked.connect(self._reparent)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_show.clicked.connect(lambda: self._sel_id() and self.show_category.emit(self._sel_id()))
        self.btn_add_prompt.clicked.connect(lambda: self._sel_id() and self.new_prompt_in.emit(self._sel_id()))
        for b in (self.btn_new, self.btn_sub, self.btn_rename, self.btn_style, self.btn_move,
                  self.btn_show, self.btn_add_prompt, self.btn_delete):
            sl.addWidget(b)
        self.cat_prompts = QListWidget()
        self.cat_prompts.itemDoubleClicked.connect(lambda it: self.open_prompt.emit(it.data(ROLE_PROMPT_ID)))
        sl.addWidget(QLabel("پرامپت‌های این دسته (دابل‌کلیک = ویرایش):"))
        sl.addWidget(self.cat_prompts, 1)
        lay.addWidget(side, 2)
        return w

    def _sel_id(self) -> int | None:
        items = self.tree.selectedItems()
        return items[0].data(0, ROLE_CAT_ID) if items else None

    def refresh(self) -> None:
        keep = self._sel_id()
        self.tree.clear()

        def add(nodes, parent_item):
            for c in nodes:
                it = QTreeWidgetItem([f"{c.icon}  {c.name}    ({c.count})"])
                it.setData(0, ROLE_CAT_ID, c.id)
                it.setIcon(0, _color_icon(c.color))
                (parent_item.addChild(it) if parent_item else self.tree.addTopLevelItem(it))
                add(c.children, it)
                if keep == c.id:
                    self.tree.setCurrentItem(it)

        add(self.ctx.categories.tree(), None)
        self.tree.expandAll()
        self._cat_selected()
        self._refresh_tags()

    def _cat_selected(self) -> None:
        cid = self._sel_id()
        has = cid is not None
        for b in (self.btn_sub, self.btn_rename, self.btn_style, self.btn_move, self.btn_delete,
                  self.btn_show, self.btn_add_prompt):
            b.setEnabled(has)
        self.cat_prompts.clear()
        if not has:
            self.cat_title.setText("یک دسته‌بندی را انتخاب کنید")
            return
        cat = self.ctx.categories.get(cid)
        if cat is None:
            return
        self.cat_title.setText(f"{cat.icon} {self.ctx.categories.path_name(cid)}")
        from ..services.search_service import PromptFilter
        for p in self.ctx.search.search(PromptFilter(category_id=cid, limit=200)):
            it = QListWidgetItem(p.title)
            it.setData(ROLE_PROMPT_ID, p.id)
            self.cat_prompts.addItem(it)

    def _add(self, parent_id: int | None) -> None:
        dlg = CategoryDialog(self, "زیردسته‌ی جدید" if parent_id else "دسته‌بندی جدید")
        if not dlg.exec():
            return
        name, icon, color = dlg.values()
        try:
            self.ctx.categories.add(name, parent_id, icon, color)
        except ValueError as e:
            error(self, "ساخت دسته‌بندی ممکن نشد", str(e))
            return
        self.changed.emit()
        self.refresh()

    def _rename(self) -> None:
        cid = self._sel_id()
        cat = self.ctx.categories.get(cid) if cid else None
        if cat is None:
            return
        name = ask_text(self, "تغییر نام دسته‌بندی", "نام جدید:", cat.name)
        if not name:
            return
        try:
            self.ctx.categories.rename(cid, name)
        except (ValueError, KeyError) as e:
            error(self, "تغییر نام ممکن نشد", str(e))
            return
        self.changed.emit()
        self.refresh()

    def _style(self) -> None:
        cid = self._sel_id()
        cat = self.ctx.categories.get(cid) if cid else None
        if cat is None:
            return
        dlg = CategoryDialog(self, "آیکون و رنگ", cat.name, cat.icon, cat.color, ask_name=False)
        if dlg.exec():
            _n, icon, color = dlg.values()
            self.ctx.categories.set_style(cid, icon, color)
            self.changed.emit()
            self.refresh()

    def _reparent(self) -> None:
        cid = self._sel_id()
        if cid is None:
            return
        dlg = MoveDialog(self.ctx, self, "انتقال دسته‌بندی به …")
        dlg.combo.setItemText(0, "سطح اصلی (بدون والد)")  # ردیف صفر همان «بدون دسته‌بندی» (مقدار None) است
        if dlg.exec():
            try:
                self.ctx.categories.reparent(cid, dlg.category_id())
            except (ValueError, KeyError) as e:
                error(self, "انتقال ممکن نشد", str(e))
                return
            self.changed.emit()
            self.refresh()

    def _delete(self) -> None:
        cid = self._sel_id()
        if cid is None:
            return
        dlg = DeleteCategoryDialog(self.ctx, cid, self)
        if not dlg.exec():
            return
        action, target = dlg.choice()
        try:
            self.ctx.categories.delete(cid, action, target)
        except (ValueError, KeyError) as e:
            error(self, "حذف ممکن نشد", str(e))
            return
        self.message.emit("دسته‌بندی حذف شد")
        self.changed.emit()
        self.refresh()

    # ---------------------------------------------------------------- برچسب‌ها
    def _build_tags(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        self.tag_list = QListWidget()
        self.tag_list.itemDoubleClicked.connect(lambda it: self.show_tag.emit(it.data(Qt.UserRole)))
        self.tag_list.itemSelectionChanged.connect(self._tag_selected)
        lay.addWidget(self.tag_list, 3)
        side = QFrame()
        side.setObjectName("panel")
        sl = QVBoxLayout(side)
        t = QLabel("مدیریت برچسب‌ها")
        t.setObjectName("h2")
        sl.addWidget(t)
        self.tag_new = QPushButton("➕ برچسب جدید")
        self.tag_show = QPushButton("📚 نمایش پرامپت‌های این برچسب")
        self.tag_rename = QPushButton("✏️ تغییر نام (در صورت هم‌نام بودن ادغام می‌شود)")
        self.tag_delete = QPushButton("🗑️ حذف برچسب")
        self.tag_delete.setObjectName("danger")
        self.tag_new.clicked.connect(self._tag_add)
        self.tag_show.clicked.connect(lambda: self._cur_tag() and self.show_tag.emit(self._cur_tag()))
        self.tag_rename.clicked.connect(self._tag_rename)
        self.tag_delete.clicked.connect(self._tag_delete)
        for b in (self.tag_new, self.tag_show, self.tag_rename, self.tag_delete):
            sl.addWidget(b)
        hint = QLabel("برچسب‌ها را هنگام ویرایش هر پرامپت هم می‌توانید بنویسید یا انتخاب کنید.\n"
                      "حذف یک برچسب فقط آن را از پرامپت‌ها برمی‌دارد؛ خود پرامپت‌ها حذف نمی‌شوند.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        sl.addWidget(hint)
        sl.addStretch(1)
        lay.addWidget(side, 2)
        return w

    def _refresh_tags(self) -> None:
        keep = self._cur_tag()
        self.tag_list.clear()
        for t in self.ctx.tags.all():
            it = QListWidgetItem(f"#{t.name}    ({t.count})")
            it.setData(Qt.UserRole, t.name)
            it.setData(ROLE_CAT_ID, t.id)
            self.tag_list.addItem(it)
            if t.name == keep:
                self.tag_list.setCurrentItem(it)
        self._tag_selected()

    def _cur_tag(self) -> str | None:
        items = self.tag_list.selectedItems()
        return items[0].data(Qt.UserRole) if items else None

    def _cur_tag_id(self) -> int | None:
        items = self.tag_list.selectedItems()
        return items[0].data(ROLE_CAT_ID) if items else None

    def _tag_selected(self) -> None:
        has = self._cur_tag() is not None
        for b in (self.tag_show, self.tag_rename, self.tag_delete):
            b.setEnabled(has)

    def _tag_add(self) -> None:
        name = ask_text(self, "برچسب جدید", "نام برچسب:")
        if name:
            try:
                self.ctx.tags.create(name)
            except ValueError as e:
                error(self, "ساخت برچسب ممکن نشد", str(e))
                return
            self.changed.emit()
            self._refresh_tags()

    def _tag_rename(self) -> None:
        tid, cur = self._cur_tag_id(), self._cur_tag()
        if tid is None:
            return
        name = ask_text(self, "تغییر نام برچسب", "نام جدید:", cur or "")
        if name:
            try:
                self.ctx.tags.rename(tid, name)
            except ValueError as e:
                error(self, "تغییر نام ممکن نشد", str(e))
                return
            self.changed.emit()
            self._refresh_tags()

    def _tag_delete(self) -> None:
        tid, cur = self._cur_tag_id(), self._cur_tag()
        if tid is None:
            return
        if confirm(self, "حذف برچسب", f"برچسب «{cur}» از همه‌ی پرامپت‌ها برداشته می‌شود. ادامه می‌دهید؟",
                   "حذف برچسب", danger=True):
            self.ctx.tags.delete(tid)
            self.changed.emit()
            self._refresh_tags()
