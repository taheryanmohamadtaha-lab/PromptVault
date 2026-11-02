"""ویجت‌های قابل استفاده‌ی مجدد: کارت آماری، پیام کوتاه (Toast)، نمایش پرامپت در فهرست با برجسته‌سازی."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QColor, QPainter, QPalette, QTextDocument
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from ..models.prompt import IMPORTANCE_LABELS
from ..utils.text import highlight_html

ROLE_PROMPT_ID = Qt.UserRole + 1


def add_shadow(widget: QWidget, blur: int = 24, dy: int = 4, alpha: int = 40) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)


class StatCard(QFrame):
    """کارت آماری قابل کلیک برای داشبورد."""
    clicked = Signal()

    def __init__(self, icon: str, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(104)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        self._icon = QLabel(icon)
        self._icon.setStyleSheet("font-size: 28pt;")
        text = QVBoxLayout()
        self._value = QLabel("0")
        self._value.setObjectName("h1")
        self._title = QLabel(title)
        self._title.setObjectName("muted")
        text.addWidget(self._value)
        text.addWidget(self._title)
        lay.addLayout(text, 1)
        lay.addWidget(self._icon)
        add_shadow(self)

    def set_value(self, value: int | str) -> None:
        self._value.setText(str(value))

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


class Toast(QLabel):
    """پیام کوتاه و محو‌شونده، مثلاً «پرامپت کپی شد»."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._anim.finished.connect(self._after_anim)
        self._fading_out = False

    def show_message(self, text: str, ms: int = 1800) -> None:
        self._anim.stop()
        self._fading_out = False
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 48)
        self._effect.setOpacity(0.0)
        self.show()
        self.raise_()
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(ms)

    def _fade_out(self) -> None:
        self._fading_out = True
        self._anim.setDuration(300)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _after_anim(self) -> None:
        if self._fading_out:
            self.hide()


class PromptDelegate(QStyledItemDelegate):
    """رسم هر پرامپت در فهرست: عنوان (با برجسته‌سازی جست‌وجو)، خلاصه‌ی متن، برچسب‌ها و نشان‌ها."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self.show_preview = True

    def _html(self, option: QStyleOptionViewItem, index) -> str:
        d = index.data(Qt.UserRole) or {}
        selected = bool(option.state & QStyle.State_Selected)
        title_color = option.palette.color(QPalette.HighlightedText if selected else QPalette.Text).name()
        muted = title_color if selected else option.palette.color(QPalette.PlaceholderText).name()
        badges = ""
        if d.get("pinned"):
            badges += "📌 "
        if d.get("favorite"):
            badges += "⭐ "
        title = highlight_html(d.get("title", ""), self.query)
        html = f'<div style="color:{title_color};font-weight:600;">{badges}{title}</div>'
        if self.show_preview:
            body = (d.get("body", "") or "").replace("\n", " ")
            snippet = body[:140] + ("…" if len(body) > 140 else "")
            html += f'<div style="color:{muted};">{highlight_html(snippet, self.query)}</div>'
        meta = []
        if d.get("category"):
            meta.append(d["category"])
        if d.get("platform"):
            meta.append(d["platform"])
        if d.get("tags"):
            meta.append(" ".join("#" + t for t in d["tags"][:5]))
        meta.append("اهمیت: " + IMPORTANCE_LABELS.get(d.get("importance", 2), ""))
        if d.get("use_count"):
            meta.append(f"{d['use_count']} بار استفاده")
        html += f'<div style="color:{muted};font-size:9pt;">{" • ".join(meta)}</div>'
        return html

    def _doc(self, option: QStyleOptionViewItem, index, width: float) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        topt = doc.defaultTextOption()
        topt.setTextDirection(Qt.RightToLeft)
        doc.setDefaultTextOption(topt)
        doc.setHtml(self._html(option, index))
        doc.setTextWidth(max(width - 20, 50))
        return doc

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        doc = self._doc(option, index, option.rect.width())
        painter.save()
        painter.translate(option.rect.left() + 10, option.rect.top() + 6)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        doc.documentLayout().draw(painter, ctx)
        painter.restore()
        opt.text = text

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802
        view = option.widget
        if view is not None and hasattr(view, "viewport") and view.viewport().width() > 50:
            width = view.viewport().width() - 12
        else:
            width = option.rect.width() if option.rect.width() > 0 else 400
        doc = self._doc(option, index, width)
        return QSize(int(width), int(doc.size().height()) + 14)


def prompt_item_data(p, category_name: str = "") -> dict:
    """داده‌ی لازم برای رسم یک پرامپت در PromptDelegate."""
    return {
        "id": p.id, "title": p.title, "body": p.body, "favorite": p.favorite, "pinned": p.pinned,
        "category": category_name, "platform": p.platform, "tags": p.tags,
        "importance": p.importance, "use_count": p.use_count,
    }


def h_line(parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Plain)
    f.setStyleSheet("color: rgba(128,128,128,60);")
    return f
