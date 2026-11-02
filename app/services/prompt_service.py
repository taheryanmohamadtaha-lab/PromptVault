"""سرویس پرامپت‌ها: ساخت، ویرایش، حذف نرم/دائمی، بازیابی، تکثیر، استفاده و آمار."""
from __future__ import annotations

import uuid as uuidlib
from typing import Iterable

from ..core.database import Database
from ..models.prompt import Prompt
from ..utils.paths import now_iso
from ..utils.text import normalize, similarity

_EDITABLE = {
    "title", "body", "category_id", "platform", "output_type", "notes",
    "status", "importance", "favorite", "pinned", "archived",
}


class PromptService:
    def __init__(self, db: Database):
        self.db = db

    # ---------- خواندن ----------
    def tags_for(self, prompt_ids: Iterable[int]) -> dict[int, list[str]]:
        ids = list(prompt_ids)
        result: dict[int, list[str]] = {i: [] for i in ids}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            rows = self.db.query(
                f"SELECT pt.prompt_id, t.name FROM prompt_tags pt JOIN tags t ON t.id = pt.tag_id "
                f"WHERE pt.prompt_id IN ({marks}) ORDER BY t.name COLLATE NOCASE",
                chunk,
            )
            for r in rows:
                result[r["prompt_id"]].append(r["name"])
        return result

    def get(self, prompt_id: int) -> Prompt | None:
        row = self.db.query_one("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        if row is None:
            return None
        return Prompt.from_row(row, self.tags_for([prompt_id])[prompt_id])

    def get_by_uuid(self, uid: str) -> Prompt | None:
        row = self.db.query_one("SELECT * FROM prompts WHERE uuid = ?", (uid,))
        if row is None:
            return None
        return Prompt.from_row(row, self.tags_for([row["id"]])[row["id"]])

    def hydrate(self, rows) -> list[Prompt]:
        tags = self.tags_for([r["id"] for r in rows])
        return [Prompt.from_row(r, tags[r["id"]]) for r in rows]

    # ---------- نوشتن ----------
    def create(
        self,
        title: str,
        body: str = "",
        category_id: int | None = None,
        tags: Iterable[str] = (),
        *,
        platform: str = "",
        output_type: str = "",
        notes: str = "",
        status: str = "فعال",
        importance: int = 2,
        favorite: bool = False,
        pinned: bool = False,
        uuid: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Prompt:
        title = (title or "").strip()
        if not title:
            raise ValueError("عنوان پرامپت نمی‌تواند خالی باشد.")
        ts = created_at or now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO prompts(uuid, title, body, category_id, platform, output_type, notes, status, "
                "importance, favorite, pinned, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid or str(uuidlib.uuid4()), title, body or "", category_id, platform.strip(),
                 output_type.strip(), notes, status, int(importance), int(favorite), int(pinned),
                 ts, updated_at or ts),
            )
            pid = cur.lastrowid
            self._set_tags(conn, pid, tags)
            conn.execute(
                "INSERT INTO versions(prompt_id, version_no, title, body, note, created_at) VALUES(?,?,?,?,?,?)",
                (pid, 1, title, body or "", "نسخه‌ی اولیه", ts),
            )
            self._reindex(conn, pid)
        self._mark_changed()
        return self.get(pid)

    def update(
        self,
        prompt_id: int,
        *,
        tags: Iterable[str] | None = None,
        version_note: str = "",
        record_version: bool = True,
        **fields,
    ) -> Prompt:
        """ویرایش پرامپت. اگر عنوان یا متن تغییر کند، یک نسخه‌ی جدید در تاریخچه ثبت می‌شود.
        ذخیره‌ی خودکار ویرایشگر با record_version=False صدا زده می‌شود و نسخه نمی‌سازد."""
        current = self.get(prompt_id)
        if current is None:
            raise KeyError("پرامپت پیدا نشد.")
        unknown = set(fields) - _EDITABLE
        if unknown:
            raise ValueError(f"فیلد نامعتبر: {', '.join(sorted(unknown))}")
        if "title" in fields:
            fields["title"] = (fields["title"] or "").strip()
            if not fields["title"]:
                raise ValueError("عنوان پرامپت نمی‌تواند خالی باشد.")
        for key in ("favorite", "pinned", "archived"):
            if key in fields:
                fields[key] = int(bool(fields[key]))
        content_changed = (
            ("title" in fields and fields["title"] != current.title)
            or ("body" in fields and fields["body"] != current.body)
        )
        with self.db.transaction() as conn:
            if fields:
                sets = ", ".join(f"{k} = ?" for k in fields)
                conn.execute(
                    f"UPDATE prompts SET {sets}, updated_at = ? WHERE id = ?",
                    [*fields.values(), now_iso(), prompt_id],
                )
            if tags is not None:
                self._set_tags(conn, prompt_id, tags)
            if content_changed and record_version:
                self._add_version(conn, prompt_id, version_note)
            self._reindex(conn, prompt_id)
        self._mark_changed()
        return self.get(prompt_id)

    def commit_version(self, prompt_id: int, note: str = "") -> bool:
        """اگر متن/عنوان فعلی با آخرین نسخه‌ی ثبت‌شده فرق دارد، یک نسخه‌ی جدید ثبت می‌کند."""
        with self.db.transaction() as conn:
            cur = conn.execute("SELECT title, body FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
            last = conn.execute(
                "SELECT title, body FROM versions WHERE prompt_id = ? ORDER BY version_no DESC LIMIT 1",
                (prompt_id,)).fetchone()
            if cur is None or (last is not None and last["title"] == cur["title"] and last["body"] == cur["body"]):
                return False
            self._add_version(conn, prompt_id, note)
        return True

    def _add_version(self, conn, prompt_id: int, note: str) -> None:
        row = conn.execute("SELECT title, body FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        nxt = conn.execute(
            "SELECT COALESCE(MAX(version_no), 0) + 1 FROM versions WHERE prompt_id = ?", (prompt_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO versions(prompt_id, version_no, title, body, note, created_at) VALUES(?,?,?,?,?,?)",
            (prompt_id, nxt, row["title"], row["body"], note or "", now_iso()),
        )

    def _set_tags(self, conn, prompt_id: int, tags: Iterable[str]) -> None:
        clean: dict[str, str] = {}
        for t in tags:
            t = (t or "").strip().lstrip("#").strip()
            if t:
                clean.setdefault(normalize(t), t)
        conn.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt_id,))
        for t in clean.values():
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (t,))
            tid = conn.execute("SELECT id FROM tags WHERE name = ?", (t,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO prompt_tags(prompt_id, tag_id) VALUES(?,?)", (prompt_id, tid))

    def reindex(self, prompt_id: int) -> None:
        with self.db.transaction() as conn:
            self._reindex(conn, prompt_id)

    def reindex_all(self) -> None:
        with self.db.transaction() as conn:
            for r in conn.execute("SELECT id FROM prompts").fetchall():
                self._reindex(conn, r["id"])

    def _reindex(self, conn, prompt_id: int) -> None:
        row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        if row is None:
            return
        cat_names: list[str] = []
        cid = row["category_id"]
        guard = 0
        while cid is not None and guard < 20:
            c = conn.execute("SELECT name, parent_id FROM categories WHERE id = ?", (cid,)).fetchone()
            if c is None:
                break
            cat_names.append(c["name"])
            cid = c["parent_id"]
            guard += 1
        tag_names = [
            r["name"] for r in conn.execute(
                "SELECT t.name FROM prompt_tags pt JOIN tags t ON t.id = pt.tag_id WHERE pt.prompt_id = ?",
                (prompt_id,),
            ).fetchall()
        ]
        text = " \n ".join(
            [row["title"], row["body"], row["notes"], row["platform"], row["output_type"], *cat_names, *tag_names]
        )
        conn.execute("UPDATE prompts SET search_text = ? WHERE id = ?", (normalize(text), prompt_id))

    # ---------- وضعیت‌ها ----------
    def set_favorite(self, prompt_id: int, value: bool) -> None:
        self._flag(prompt_id, "favorite", value)

    def set_pinned(self, prompt_id: int, value: bool) -> None:
        self._flag(prompt_id, "pinned", value)

    def set_archived(self, prompt_id: int, value: bool) -> None:
        self._flag(prompt_id, "archived", value)

    def _flag(self, prompt_id: int, column: str, value: bool) -> None:
        assert column in ("favorite", "pinned", "archived")
        self.db.execute(f"UPDATE prompts SET {column} = ? WHERE id = ?", (int(bool(value)), prompt_id))
        self._mark_changed()

    def move(self, prompt_ids: Iterable[int], category_id: int | None) -> None:
        ids = list(prompt_ids)
        with self.db.transaction() as conn:
            if category_id is not None and conn.execute(
                "SELECT 1 FROM categories WHERE id = ?", (category_id,)
            ).fetchone() is None:
                raise KeyError("دسته‌بندی مقصد پیدا نشد.")
            for pid in ids:
                conn.execute(
                    "UPDATE prompts SET category_id = ?, updated_at = ? WHERE id = ?",
                    (category_id, now_iso(), pid),
                )
                self._reindex(conn, pid)
        self._mark_changed()

    def mark_used(self, prompt_id: int) -> None:
        """ثبت یک بار استفاده/کپی: شمارنده و تاریخ آخرین استفاده."""
        self.db.execute(
            "UPDATE prompts SET use_count = use_count + 1, last_used_at = ? WHERE id = ?",
            (now_iso(), prompt_id),
        )
        self._mark_changed()

    # ---------- حذف و بازیابی ----------
    def trash(self, prompt_ids: Iterable[int]) -> None:
        """حذف نرم: به سطل بازیافت منتقل می‌شود و قابل بازیابی است."""
        with self.db.transaction() as conn:
            for pid in prompt_ids:
                conn.execute("UPDATE prompts SET deleted_at = ? WHERE id = ?", (now_iso(), pid))
        self._mark_changed()

    def restore(self, prompt_ids: Iterable[int]) -> None:
        with self.db.transaction() as conn:
            for pid in prompt_ids:
                conn.execute("UPDATE prompts SET deleted_at = NULL WHERE id = ?", (pid,))
        self._mark_changed()

    def purge(self, prompt_ids: Iterable[int], file_service=None) -> None:
        """حذف دائمی (فقط پس از تأیید کاربر در رابط). پیوست‌های دیسک هم پاک می‌شوند."""
        ids = list(prompt_ids)
        if file_service is not None:
            for pid in ids:
                file_service.delete_files_of_prompt(pid)
        with self.db.transaction() as conn:
            for pid in ids:
                conn.execute("DELETE FROM prompts WHERE id = ?", (pid,))
            conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM prompt_tags)")
        self._mark_changed()

    def empty_trash(self, file_service=None) -> int:
        ids = [r["id"] for r in self.db.query("SELECT id FROM prompts WHERE deleted_at IS NOT NULL")]
        self.purge(ids, file_service)
        return len(ids)

    # ---------- تکثیر ----------
    def duplicate(self, prompt_id: int) -> Prompt:
        src = self.get(prompt_id)
        if src is None:
            raise KeyError("پرامپت پیدا نشد.")
        return self.create(
            f"{src.title} (کپی)", src.body, src.category_id, src.tags,
            platform=src.platform, output_type=src.output_type, notes=src.notes,
            status=src.status, importance=src.importance,
        )

    # ---------- آمار و پیشنهاد ----------
    def stats(self) -> dict[str, int]:
        q = lambda sql: self.db.query_one(sql)[0]  # noqa: E731
        live = "deleted_at IS NULL"
        return {
            "total": q(f"SELECT COUNT(*) FROM prompts WHERE {live} AND archived = 0"),
            "archived": q(f"SELECT COUNT(*) FROM prompts WHERE {live} AND archived = 1"),
            "trash": q("SELECT COUNT(*) FROM prompts WHERE deleted_at IS NOT NULL"),
            "categories": q("SELECT COUNT(*) FROM categories"),
            "tags": q("SELECT COUNT(*) FROM tags"),
            "favorites": q(f"SELECT COUNT(*) FROM prompts WHERE {live} AND favorite = 1"),
            "pinned": q(f"SELECT COUNT(*) FROM prompts WHERE {live} AND pinned = 1"),
            "recent_used": q(f"SELECT COUNT(*) FROM prompts WHERE {live} AND last_used_at IS NOT NULL"),
            "never_used": q(f"SELECT COUNT(*) FROM prompts WHERE {live} AND use_count = 0"),
            "total_uses": q(f"SELECT COALESCE(SUM(use_count), 0) FROM prompts WHERE {live}"),
        }

    def similar(self, prompt_id: int, limit: int = 5) -> list[Prompt]:
        """پرامپت‌های مشابه بر اساس برچسب مشترک و شباهت عنوان (کاملاً محلی)."""
        base = self.get(prompt_id)
        if base is None:
            return []
        rows = self.db.query(
            "SELECT * FROM prompts WHERE deleted_at IS NULL AND id != ?", (prompt_id,)
        )
        cands = self.hydrate(rows)
        base_tags = {normalize(t) for t in base.tags}
        scored: list[tuple[float, Prompt]] = []
        for p in cands:
            tags = {normalize(t) for t in p.tags}
            tag_score = len(base_tags & tags) / len(base_tags | tags) if base_tags and tags else 0.0
            score = 0.6 * tag_score + 0.4 * similarity(base.title, p.title)
            if p.category_id is not None and p.category_id == base.category_id:
                score += 0.05
            if score > 0.08:
                scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    def find_exact_duplicate(self, title: str, body: str) -> Prompt | None:
        row = self.db.query_one(
            "SELECT * FROM prompts WHERE title = ? AND body = ? LIMIT 1", (title.strip(), body)
        )
        return self.hydrate([row])[0] if row else None

    def find_same_title(self, title: str) -> Prompt | None:
        row = self.db.query_one("SELECT * FROM prompts WHERE title = ? LIMIT 1", (title.strip(),))
        return self.hydrate([row])[0] if row else None

    # ---------- داخلی ----------
    def _mark_changed(self) -> None:
        self.db.execute(
            "INSERT INTO settings(key, value) VALUES('data_changed_since_backup', 'true') "
            "ON CONFLICT(key) DO UPDATE SET value = 'true'"
        )
