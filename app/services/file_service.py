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
    # کد و فایل‌های نهایی که هوش مصنوعی می‌سازد
    ".kt", ".java", ".cs", ".cpp", ".c", ".h", ".hpp", ".swift", ".ts", ".tsx", ".jsx", ".vue", ".php",
    ".go", ".rs", ".rb", ".lua", ".sql", ".log", ".ini", ".toml", ".gradle", ".svg",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
KINDS = ("file", "image", "result")
# فقط این پسوندها با برنامه‌ی پیش‌فرض ویندوز باز می‌شوند؛ کد و اسکریپت (js، py، html، …) هرگز اجرا نمی‌شوند.
SAFE_OPEN_EXTENSIONS = IMAGE_EXTENSIONS | {
    ".pdf", ".txt", ".md", ".docx", ".doc", ".rtf", ".odt", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".log", ".ini", ".toml", ".xlsx", ".pptx", ".mp3", ".mp4", ".wav",
}
MAX_TEXT_PREVIEW = 2 * 1024 * 1024  # حداکثر ۲ مگابایت برای نمایش متن
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

    @staticmethod
    def _check_kind(kind: str, ext: str) -> None:
        if kind not in KINDS:
            raise ValueError("نوع پیوست نامعتبر است.")
        if kind == "image" and ext not in IMAGE_EXTENSIONS:
            raise ValueError("برای تصویر فقط PNG، JPG، GIF، WEBP و BMP مجاز است.")

    def add(self, prompt_id: int, source: str | Path, kind: str = "file") -> Attachment:
        src = Path(source)
        if not src.is_file():
            raise FileNotFoundError("فایل انتخاب‌شده پیدا نشد.")
        ext = src.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"فرمت «{ext or 'بدون پسوند'}» برای پیوست مجاز نیست.")
        self._check_kind(kind, ext)
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
                "INSERT INTO attachments(prompt_id, filename, stored_name, size, sha256, created_at, kind) "
                "VALUES(?,?,?,?,?,?,?)",
                (prompt_id, src.name, stored, size, self._sha256(dest), now_iso(), kind))
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        return self.get(cur.lastrowid)

    def add_bytes(self, prompt_id: int, filename: str, data: bytes, created_at: str | None = None,
                  kind: str = "file") -> Attachment:
        """برای بازیابی بکاپ: ورود پیوست از داده‌ی خام (با همان اعتبارسنجی‌ها)."""
        name = Path(filename).name  # هرگونه مسیر حذف می‌شود
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"فرمت «{ext}» مجاز نیست.")
        self._check_kind(kind, ext)
        if len(data) > MAX_SIZE:
            raise ValueError("حجم فایل بیش از حد مجاز (۱۰۰ مگابایت) است.")
        if self.db.query_one("SELECT 1 FROM prompts WHERE id = ?", (prompt_id,)) is None:
            raise KeyError("پرامپت پیدا نشد.")
        stored = f"{uuidlib.uuid4().hex}{ext}"
        dest = self.dir / stored
        dest.write_bytes(data)
        try:
            cur = self.db.execute(
                "INSERT INTO attachments(prompt_id, filename, stored_name, size, sha256, created_at, kind) "
                "VALUES(?,?,?,?,?,?,?)",
                (prompt_id, name, stored, len(data), hashlib.sha256(data).hexdigest(),
                 created_at or now_iso(), kind))
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        return self.get(cur.lastrowid)

    def add_text(self, prompt_id: int, filename: str, text: str, kind: str = "result") -> Attachment:
        """ذخیره‌ی متن/کد (مثلاً چسبانده‌شده از کلیپ‌بورد) به‌صورت فایل UTF-8."""
        if not text.strip():
            raise ValueError("متن خالی است.")
        name = Path(filename).name.strip() or "result.txt"
        if not Path(name).suffix:
            name += ".txt"
        return self.add_bytes(prompt_id, name, text.encode("utf-8"), kind=kind)

    def read_text(self, att: Attachment) -> str | None:
        """متن فایل برای نمایش؛ اگر فایل باینری یا بسیار بزرگ باشد None."""
        path = self.path_of(att)
        if not path.is_file() or path.stat().st_size > MAX_TEXT_PREVIEW:
            return None
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            return None
        return raw.decode("utf-8", errors="replace")

    def get(self, attachment_id: int) -> Attachment | None:
        row = self.db.query_one("SELECT * FROM attachments WHERE id = ?", (attachment_id,))
        return Attachment.from_row(row) if row else None

    def list(self, prompt_id: int, kind: str | None = None) -> list[Attachment]:
        if kind is None:
            rows = self.db.query("SELECT * FROM attachments WHERE prompt_id = ? ORDER BY id", (prompt_id,))
        else:
            rows = self.db.query(
                "SELECT * FROM attachments WHERE prompt_id = ? AND kind = ? ORDER BY id", (prompt_id, kind))
        return [Attachment.from_row(r) for r in rows]

    def path_of(self, att: Attachment) -> Path:
        p = (self.dir / att.stored_name).resolve()
        if self.dir.resolve() not in p.parents:  # دفاع در برابر مسیر مخرب
            raise ValueError("مسیر فایل نامعتبر است.")
        return p

    @staticmethod
    def is_safe_to_open(att: Attachment) -> bool:
        return Path(att.stored_name).suffix.lower() in SAFE_OPEN_EXTENSIONS

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
