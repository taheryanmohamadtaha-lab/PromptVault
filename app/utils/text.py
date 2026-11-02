"""ابزارهای متنی: نرمال‌سازی فارسی برای جست‌وجو، شمارش کلمات و برجسته‌سازی."""
from __future__ import annotations

import html
import re

_ARABIC_TO_PERSIAN = {
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "أ": "ا",
    "إ": "ا",
    "ؤ": "و",
}
_DIGITS = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۭـ]")  # اعراب و کشیده
_ZWNJ = "‌"
_SPACES = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """متن را برای جست‌وجو یکدست می‌کند (ی/ک عربی، اعراب، ارقام، نیم‌فاصله، حروف بزرگ)."""
    if not text:
        return ""
    for src, dst in _ARABIC_TO_PERSIAN.items():
        text = text.replace(src, dst)
    text = _DIACRITICS.sub("", text)
    text = text.translate(_DIGITS)
    text = text.replace(_ZWNJ, " ")
    text = _SPACES.sub(" ", text)
    return text.casefold().strip()


def word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(re.findall(r"\S+", text))


def char_count(text: str | None) -> int:
    return len(text or "")


def highlight_html(text: str, query: str, color: str = "#FFE066") -> str:
    """متن را HTML-escape می‌کند و کلمات جست‌وجوشده را برجسته می‌کند."""
    escaped = html.escape(text or "")
    words = [w for w in normalize(query).split(" ") if w]
    if not words:
        return escaped
    # نرمال‌سازی طول‌نگه‌دار: فقط جایگزینی کاراکترها (بدون حذف) تا اندیس‌ها یکی بمانند
    folded = _fold_same_length(escaped)
    spans: list[tuple[int, int]] = []
    for w in words:
        wf = _fold_same_length(html.escape(w))
        if not wf:
            continue
        start = 0
        while True:
            i = folded.find(wf, start)
            if i < 0:
                break
            spans.append((i, i + len(wf)))
            start = i + len(wf)
    if not spans:
        return escaped
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out, pos = [], 0
    for s, e in merged:
        out.append(escaped[pos:s])
        out.append(f'<span style="background-color:{color};color:#000;">{escaped[s:e]}</span>')
        pos = e
    out.append(escaped[pos:])
    return "".join(out)


def _fold_same_length(text: str) -> str:
    """نسخه‌ی طول‌نگه‌دار نرمال‌سازی (هر کاراکتر دقیقاً یک کاراکتر می‌ماند)."""
    out = []
    for ch in text:
        ch = _ARABIC_TO_PERSIAN.get(ch, ch)
        ch = ch.translate(_DIGITS)
        if ch == _ZWNJ:
            ch = " "
        low = ch.casefold()
        out.append(low if len(low) == 1 else ch)
    return "".join(out)


def similarity(a: str, b: str) -> float:
    """شباهت ساده‌ی کلمه‌ای (Jaccard) برای تشخیص پرامپت‌های مشابه، بدون نیاز به API."""
    sa = set(normalize(a).split())
    sb = set(normalize(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
