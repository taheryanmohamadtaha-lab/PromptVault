"""سرویس برچسب‌ها."""
from __future__ import annotations

from ..core.database import Database
from ..models.tag import Tag
from ..utils.text import normalize


class TagService:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> list[Tag]:
        rows = self.db.query(
            "SELECT t.id, t.name, COUNT(p.id) AS n FROM tags t "
            "LEFT JOIN prompt_tags pt ON pt.tag_id = t.id "
            "LEFT JOIN prompts p ON p.id = pt.prompt_id AND p.deleted_at IS NULL "
            "GROUP BY t.id ORDER BY t.name COLLATE NOCASE"
        )
        return [Tag(r["id"], r["name"], r["n"]) for r in rows]

    def create(self, name: str) -> Tag:
        name = (name or "").strip().lstrip("#").strip()
        if not name:
            raise ValueError("نام برچسب نمی‌تواند خالی باشد.")
        self.db.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
        row = self.db.query_one("SELECT id, name FROM tags WHERE name = ?", (name,))
        return Tag(row["id"], row["name"], 0)

    def rename(self, tag_id: int, new_name: str) -> None:
        """تغییر نام؛ اگر برچسب هم‌نام وجود داشته باشد، دو برچسب ادغام می‌شوند."""
        new_name = (new_name or "").strip().lstrip("#").strip()
        if not new_name:
            raise ValueError("نام برچسب نمی‌تواند خالی باشد.")
        with self.db.transaction() as conn:
            other = conn.execute(
                "SELECT id FROM tags WHERE name = ? AND id != ?", (new_name, tag_id)).fetchone()
            if other:
                conn.execute(
                    "INSERT OR IGNORE INTO prompt_tags(prompt_id, tag_id) "
                    "SELECT prompt_id, ? FROM prompt_tags WHERE tag_id = ?", (other["id"], tag_id))
                conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            else:
                conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id))
            affected = conn.execute(
                "SELECT DISTINCT prompt_id FROM prompt_tags WHERE tag_id IN (?, ?)",
                (tag_id, other["id"] if other else tag_id)).fetchall()
            from .prompt_service import PromptService
            helper = PromptService.__new__(PromptService)
            for r in affected:
                helper._reindex(conn, r["prompt_id"])

    def delete(self, tag_id: int) -> None:
        with self.db.transaction() as conn:
            affected = [r["prompt_id"] for r in conn.execute(
                "SELECT prompt_id FROM prompt_tags WHERE tag_id = ?", (tag_id,)).fetchall()]
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            from .prompt_service import PromptService
            helper = PromptService.__new__(PromptService)
            for pid in affected:
                helper._reindex(conn, pid)

    def suggest(self, prefix: str, limit: int = 8) -> list[str]:
        p = normalize(prefix)
        return [t.name for t in self.all() if p in normalize(t.name)][:limit]
