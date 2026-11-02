"""تاریخچه‌ی نسخه‌های پرامپت: مشاهده، مقایسه (diff)، یادداشت و بازیابی."""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from ..core.database import Database
from .prompt_service import PromptService


@dataclass
class Version:
    id: int
    prompt_id: int
    version_no: int
    title: str
    body: str
    note: str
    created_at: str


class VersionService:
    def __init__(self, db: Database, prompts: PromptService):
        self.db = db
        self.prompts = prompts

    @staticmethod
    def _v(row) -> Version:
        return Version(row["id"], row["prompt_id"], row["version_no"], row["title"],
                       row["body"], row["note"], row["created_at"])

    def list(self, prompt_id: int) -> list[Version]:
        rows = self.db.query(
            "SELECT * FROM versions WHERE prompt_id = ? ORDER BY version_no DESC", (prompt_id,))
        return [self._v(r) for r in rows]

    def get(self, prompt_id: int, version_no: int) -> Version | None:
        row = self.db.query_one(
            "SELECT * FROM versions WHERE prompt_id = ? AND version_no = ?", (prompt_id, version_no))
        return self._v(row) if row else None

    def set_note(self, version_id: int, note: str) -> None:
        self.db.execute("UPDATE versions SET note = ? WHERE id = ?", (note, version_id))

    def restore(self, prompt_id: int, version_no: int):
        """بازیابی یک نسخه‌ی قدیمی. نسخه‌ی فعلی از بین نمی‌رود؛ بازیابی خودش یک نسخه‌ی جدید ثبت می‌کند."""
        v = self.get(prompt_id, version_no)
        if v is None:
            raise KeyError("این نسخه پیدا نشد.")
        return self.prompts.update(
            prompt_id, title=v.title, body=v.body, version_note=f"بازیابی از نسخه‌ی {version_no}")

    @staticmethod
    def diff_lines(old: str, new: str) -> list[tuple[str, str]]:
        """فهرست (نوع, خط) با نوع‌های same / add / del / info برای نمایش مقایسه."""
        out: list[tuple[str, str]] = []
        for line in difflib.ndiff(old.splitlines(), new.splitlines()):
            tag, text = line[:2], line[2:]
            if tag == "  ":
                out.append(("same", text))
            elif tag == "+ ":
                out.append(("add", text))
            elif tag == "- ":
                out.append(("del", text))
            # خطوط راهنمای '? ' نادیده گرفته می‌شوند
        return out

    @staticmethod
    def diff_html(old: str, new: str) -> str:
        import html
        colors = {"same": "", "add": "background:#1f6f3a33;", "del": "background:#a8323233;"}
        sign = {"same": "&nbsp;&nbsp;", "add": "+&nbsp;", "del": "−&nbsp;"}
        rows = []
        for kind, text in VersionService.diff_lines(old, new):
            rows.append(f'<div style="{colors[kind]}white-space:pre-wrap;">{sign[kind]}{html.escape(text)}</div>')
        return "".join(rows) or "<div>(بدون تفاوت)</div>"
