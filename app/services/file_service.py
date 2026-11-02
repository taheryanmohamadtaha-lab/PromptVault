"""پیوست‌ها: ذخیره در پوشه‌ی مدیریت‌شده‌ی برنامه و ارتباط با پرامپت."""
from __future__ import annotations

import hashlib
import shutil
import uuid as uuidlib
from pathlib import Path

from ..core.database import Database
from ..models.attachment import Attachment
from ..utils.paths import now_iso

ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".pdf", ".txt", ".md", ".docx", ".doc", ".rtf", ".odt",
    ".csv", ".json", ".xml", ".yaml", ".yml", ".zip",
    ".mq4", ".mq5", ".mqh", ".ex4", ".ex5", ".pine", ".py", ".js", ".html", ".css",
    ".xlsx", ".pptx", ".mp3", ".mp4", ".wav",
}
MAX_SIZE = 100 * 1024 * 1024  # ۱۰۰ مگابایت


class FileService:
    def __init__(self, db: Database, attachments_dir: str | Path):
        self.db = db
        self.dir = Path(attachments_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def add(self, prompt_id: int, source: str | Path) -> Attachment:
        src = Path(source)
        if not src.is_file():
            raise FileNotFoundError("فایل انتخاب‌شده پیدا نشد.")
        ext = src.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"فرمت «{ext or 'بدون پسوند'}» برای پیوست مجاز نیست.")
        size = src.stat().st_size
        if size > MAX_SIZE:
            raise ValueError("حجم فایل بیش از حد مجاز (۱۰۰ مگابایت) است.")
        if self.db.query_one("SELECT 1 FROM prompts WHERE id = ?", (prompt_id,)) is None:
            raise KeyError("پرامپت پیدا نشد.")
        stored = f"{uuidlib.uuid4().hex}{ext}"
        dest = self.dir / stored
        shutil.copy2(src, dest)
        try:
            cur = self.db.execute(
                "INSERT INTO attachments(prompt_id, filename, stored_name, size, sha256, created_at) "
                "VALUES(?,?,?,?,?,?)",
                (prompt_id, src.name, stored, size, self._sha256(dest), now_iso()))
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        return self.get(cur.lastrowid)

    def add_bytes(self, prompt_id: int, filename: str, data: bytes, created_at: str | None = None) -> Attachment:
        """برای بازیابی بکاپ: ورود پیوست از داده‌ی خام (با همان اعتبارسنجی‌ها)."""
        name = Path(filename).name  # هرگونه مسیر حذف می‌شود
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"فرمت «{ext}» مجاز نیست.")
        stored = f"{uuidlib.uuid4().hex}{ext}"
        dest = self.dir / stored
        dest.write_bytes(data)
        cur = self.db.execute(
            "INSERT INTO attachments(prompt_id, filename, stored_name, size, sha256, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (prompt_id, name, stored, len(data), hashlib.sha256(data).hexdigest(), created_at or now_iso()))
        return self.get(cur.lastrowid)

    def get(self, attachment_id: int) -> Attachment | None:
        row = self.db.query_one("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
        return Attachment.from_row(row) if row else None

    def list(self, prompt_id: int) -> list[Attachment]:
        return [Attachment.from_row(r) for r in self.db.query(
            "SELECT * FROM attachments WHERE prompt_id = ? ORDER BY id", (prompt_id,))]

    def path_of(self, att: Attachment) -> Path:
        p = (self.dir / att.stored_name).resolve()
        if self.dir.resolve() not in p.parents:  # دفاع در برابر مسیر مخرب
            raise ValueError("مسیر فایل نامعتبر است.")
        return p

    def exists(self, att: Attachment) -> bool:
        return self.path_of(att).is_file()

    def delete(self, attachment_id: int) -> None:
        att = self.get(attachment_id)
        if att is None:
            return
        self.db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        self.path_of(att).unlink(missing_ok=True)

    def delete_files_of_prompt(self, prompt_id: int) -> None:
        for att in self.list(prompt_id):
            self.path_of(att).unlink(missing_ok=True)

    def export_copy(self, att: Attachment, dest_dir: str | Path) -> Path:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / att.filename
        i = 1
        while dest.exists():
            dest = dest_dir / f"{Path(att.filename).stem}_{i}{Path(att.filename).suffix}"
            i += 1
        shutil.copy2(self.path_of(att), dest)
        return dest
