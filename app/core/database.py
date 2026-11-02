"""لایه‌ی دیتابیس SQLite: ساخت جدول‌ها، مهاجرت نسخه، تراکنش امن و پشتیبان‌گیری."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    icon        TEXT NOT NULL DEFAULT '📁',
    color       TEXT NOT NULL DEFAULT '#6C63FF',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE prompts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL DEFAULT '',
    category_id   INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    platform      TEXT NOT NULL DEFAULT '',
    output_type   TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'فعال',
    importance    INTEGER NOT NULL DEFAULT 2,
    favorite      INTEGER NOT NULL DEFAULT 0,
    pinned        INTEGER NOT NULL DEFAULT 0,
    archived      INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    use_count     INTEGER NOT NULL DEFAULT 0,
    last_used_at  TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    search_text   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_prompts_category ON prompts(category_id);
CREATE INDEX idx_prompts_updated  ON prompts(updated_at);
CREATE INDEX idx_prompts_deleted  ON prompts(deleted_at);

CREATE TABLE tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE prompt_tags (
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (prompt_id, tag_id)
);

CREATE TABLE versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id   INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_no  INTEGER NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    UNIQUE (prompt_id, version_no)
);

CREATE TABLE templates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    category_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE attachments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id    INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    stored_name  TEXT NOT NULL UNIQUE,
    size         INTEGER NOT NULL DEFAULT 0,
    sha256       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_MIGRATIONS = {1: _SCHEMA_V1}


class Database:
    """اتصال امن و ساده به SQLite با تراکنش‌های خودکار."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        try:
            self._conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    # ---------- مهاجرت ----------
    def _migrate(self) -> None:
        with self._lock:
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise RuntimeError(
                    "این پایگاه داده توسط نسخه‌ی جدیدتری از برنامه ساخته شده است. "
                    "لطفاً برنامه را به‌روزرسانی کنید."
                )
            for version in range(current + 1, SCHEMA_VERSION + 1):
                self._conn.executescript("BEGIN;" + _MIGRATIONS[version] + f"PRAGMA user_version = {version};COMMIT;")

    # ---------- اجرا ----------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """تراکنش اتمی: یا همه‌ی تغییرات ذخیره می‌شوند یا هیچ‌کدام."""
        with self._lock:
            if self._conn.in_transaction:  # تراکنش تو در تو: همان تراکنش بیرونی
                yield self._conn
                return
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            # باید «قبل» از اجرا بسنجیم: اجرای DML خودش تراکنش ضمنی باز می‌کند.
            inside_explicit = self._conn.in_transaction
            cur = self._conn.execute(sql, params)
            if not inside_explicit:
                self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # ---------- پشتیبان و سلامت ----------
    def snapshot_to(self, dest: str | Path) -> Path:
        """یک نسخه‌ی کاملاً سازگار از دیتابیس زنده (حتی در حال استفاده) می‌سازد."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        with self._lock:
            target = sqlite3.connect(str(dest))
            try:
                self._conn.backup(target)
            finally:
                target.close()
        return dest

    def integrity_ok(self) -> bool:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            finally:
                self._conn.close()
