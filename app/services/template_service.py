"""قالب‌های آماده با متغیرهای {{NAME}}."""
from __future__ import annotations

import re
import uuid as uuidlib

from ..core.database import Database
from ..models.template import Template
from ..utils.paths import now_iso

_NS = uuidlib.UUID("6f1c7e0e-5a53-4d6c-9a4e-0f6f2f5d7a11")
VAR_RE = re.compile(r"\{\{\s*([A-Za-z_؀-ۿ][\w؀-ۿ]*)\s*\}\}")

STARTER_TEMPLATES = [
    ("ساخت اپلیکیشن اندروید",
     "یک اپلیکیشن اندروید به نام {{APP_NAME}} بساز.\nزبان برنامه: {{LANGUAGE}}\nسیستم‌عامل هدف: {{PLATFORM}}\n"
     "ویژگی‌های اصلی:\n{{FEATURES}}\n\nکد کامل و قابل اجرا تحویل بده.",
     "قالب عمومی برای درخواست ساخت اپلیکیشن"),
    ("ساخت اندیکاتور MT5",
     "یک اندیکاتور MetaTrader 5 به نام {{INDICATOR_NAME}} با زبان MQL5 بنویس.\nاستراتژی:\n{{STRATEGY}}\n"
     "تنظیمات ورودی قابل تغییر باشد و کد بدون خطای کامپایل باشد.",
     "قالب برای اندیکاتورهای MT5"),
    ("تولید تصویر با هوش مصنوعی",
     "{{SUBJECT}}, {{GRAPHIC_STYLE}}, lighting: {{LIGHTING}}, aspect ratio {{RATIO}}, highly detailed",
     "قالب پرامپت تصویر"),
    ("تدوین ویدیو",
     "یک ویدیوی {{DURATION}} ثانیه‌ای درباره‌ی {{TOPIC}} با سبک {{GRAPHIC_STYLE}} و موسیقی {{MUSIC}} بساز.",
     "قالب پرامپت ویدیو"),
]


def extract_variables(body: str) -> list[str]:
    """نام متغیرها به ترتیب اولین ظهور، بدون تکرار."""
    seen: list[str] = []
    for m in VAR_RE.finditer(body or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def render(body: str, values: dict[str, str]) -> str:
    """متغیرهای مقداردهی‌شده جایگزین می‌شوند؛ متغیر خالی دست‌نخورده می‌ماند تا فراموش نشود."""
    def repl(m: re.Match) -> str:
        v = values.get(m.group(1), "")
        return v if v != "" else m.group(0)
    return VAR_RE.sub(repl, body or "")


class TemplateService:
    def __init__(self, db: Database):
        self.db = db

    def seed_defaults(self) -> None:
        if self.db.query_one("SELECT 1 FROM settings WHERE key = 'templates_seeded'"):
            return
        with self.db.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0:
                for title, body, desc in STARTER_TEMPLATES:
                    ts = now_iso()
                    conn.execute(
                        "INSERT INTO templates(uuid, title, body, description, created_at, updated_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (str(uuidlib.uuid5(_NS, "template:" + title)), title, body, desc, ts, ts))
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('templates_seeded', 'true')")

    def list(self) -> list[Template]:
        return [Template.from_row(r) for r in self.db.query(
            "SELECT * FROM templates ORDER BY title COLLATE NOCASE")]

    def get(self, template_id: int) -> Template | None:
        row = self.db.query_one("SELECT * FROM templates WHERE id = ?", (template_id,))
        return Template.from_row(row) if row else None

    def create(self, title: str, body: str, description: str = "", category_id: int | None = None,
               uuid: str | None = None, created_at: str | None = None, updated_at: str | None = None) -> Template:
        title = (title or "").strip()
        if not title:
            raise ValueError("عنوان قالب نمی‌تواند خالی باشد.")
        ts = created_at or now_iso()
        cur = self.db.execute(
            "INSERT INTO templates(uuid, title, body, description, category_id, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (uuid or str(uuidlib.uuid4()), title, body or "", description, category_id, ts, updated_at or ts))
        return self.get(cur.lastrowid)

    def update(self, template_id: int, title: str, body: str, description: str = "",
               category_id: int | None = None) -> Template:
        title = (title or "").strip()
        if not title:
            raise ValueError("عنوان قالب نمی‌تواند خالی باشد.")
        self.db.execute(
            "UPDATE templates SET title = ?, body = ?, description = ?, category_id = ?, updated_at = ? WHERE id = ?",
            (title, body, description, category_id, now_iso(), template_id))
        return self.get(template_id)

    def duplicate(self, template_id: int) -> Template:
        t = self.get(template_id)
        if t is None:
            raise KeyError("قالب پیدا نشد.")
        return self.create(f"{t.title} (کپی)", t.body, t.description, t.category_id)

    def delete(self, template_id: int) -> None:
        self.db.execute("DELETE FROM templates WHERE id = ?", (template_id,))
