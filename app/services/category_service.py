"""سرویس دسته‌بندی‌های درختی."""
from __future__ import annotations

import uuid as uuidlib

_NS = uuidlib.UUID("6f1c7e0e-5a53-4d6c-9a4e-0f6f2f5d7a11")  # شناسه‌ی ثابت پیش‌فرض‌ها روی همه‌ی نصب‌ها

from ..core.database import Database
from ..models.category import Category
from ..utils.paths import now_iso

DEFAULT_CATEGORIES = [
    ("تصاویر هوش مصنوعی", "🎨", "#E040FB"),
    ("ویدیو و انیمیشن", "🎬", "#FF5252"),
    ("اپلیکیشن اندروید", "🤖", "#4CAF50"),
    ("اپلیکیشن iOS", "🍎", "#90A4AE"),
    ("بازی‌سازی", "🎮", "#FF9800"),
    ("نرم‌افزار ویندوز", "🪟", "#2196F3"),
    ("اندیکاتورهای MT4", "📈", "#26A69A"),
    ("اندیکاتورهای MT5", "📊", "#00BCD4"),
    ("Pine Script و TradingView", "📉", "#3F51B5"),
    ("اکسپرت و ربات معاملاتی", "⚙️", "#795548"),
    ("هوش مصنوعی", "🧠", "#9C27B0"),
    ("طراحی سایت", "🌐", "#03A9F4"),
    ("افزونه مرورگر", "🧩", "#8BC34A"),
    ("نویسندگی و تولید محتوا", "✍️", "#FFC107"),
    ("سایر موارد", "📦", "#607D8B"),
]


class CategoryService:
    def __init__(self, db: Database):
        self.db = db

    # ---------- مقداردهی اولیه ----------
    def seed_defaults(self) -> bool:
        """دسته‌بندی‌های پیش‌فرض را فقط یک بار (در اولین اجرا) می‌سازد."""
        if self.db.query_one("SELECT 1 FROM settings WHERE key = 'defaults_seeded'"):
            return False
        with self.db.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
                for i, (name, icon, color) in enumerate(DEFAULT_CATEGORIES):
                    conn.execute(
                        "INSERT INTO categories(uuid, name, parent_id, icon, color, sort_order, created_at) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (str(uuidlib.uuid5(_NS, "category:" + name)), name, None, icon, color, i, now_iso()),
                    )
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('defaults_seeded', 'true')")
        return True

    def restore_missing_defaults(self) -> int:
        """دسته‌بندی‌های پیش‌فرضی که حذف شده‌اند را دوباره می‌سازد (بدون دست زدن به بقیه)."""
        existing = {r["name"] for r in self.db.query("SELECT name FROM categories")}
        added = 0
        with self.db.transaction() as conn:
            base = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM categories").fetchone()[0]
            for name, icon, color in DEFAULT_CATEGORIES:
                if name not in existing:
                    base += 1
                    conn.execute(
                        "INSERT INTO categories(uuid, name, parent_id, icon, color, sort_order, created_at) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (str(uuidlib.uuid5(_NS, "category:" + name)), name, None, icon, color, base, now_iso()),
                    )
                    added += 1
        return added

    # ---------- خواندن ----------
    def get(self, category_id: int) -> Category | None:
        row = self.db.query_one("SELECT * FROM categories WHERE id = ?", (category_id,))
        return Category.from_row(row) if row else None

    def flat(self) -> list[Category]:
        counts = {
            r["category_id"]: r["n"] for r in self.db.query(
                "SELECT category_id, COUNT(*) AS n FROM prompts "
                "WHERE deleted_at IS NULL AND archived = 0 AND category_id IS NOT NULL GROUP BY category_id"
            )
        }
        rows = self.db.query("SELECT * FROM categories ORDER BY sort_order, id")
        return [Category.from_row(r, counts.get(r["id"], 0)) for r in rows]

    def tree(self) -> list[Category]:
        """درخت دسته‌بندی‌ها؛ count هر گره شامل پرامپت‌های زیردسته‌ها هم هست."""
        flat = self.flat()
        by_id = {c.id: c for c in flat}
        roots: list[Category] = []
        for c in flat:
            parent = by_id.get(c.parent_id) if c.parent_id else None
            (parent.children if parent else roots).append(c)

        def total(node: Category) -> int:
            node.count += sum(total(ch) for ch in node.children)
            return node.count

        for r in roots:
            total(r)
        return roots

    def descendant_ids(self, category_id: int) -> list[int]:
        ids = [category_id]
        frontier = [category_id]
        while frontier:
            marks = ",".join("?" * len(frontier))
            rows = self.db.query(f"SELECT id FROM categories WHERE parent_id IN ({marks})", frontier)
            frontier = [r["id"] for r in rows if r["id"] not in ids]
            ids.extend(frontier)
        return ids

    def path_name(self, category_id: int | None) -> str:
        names: list[str] = []
        cid, guard = category_id, 0
        while cid is not None and guard < 20:
            row = self.db.query_one("SELECT name, parent_id FROM categories WHERE id = ?", (cid,))
            if row is None:
                break
            names.append(row["name"])
            cid = row["parent_id"]
            guard += 1
        return " ‹ ".join(reversed(names))

    # ---------- نوشتن ----------
    def add(self, name: str, parent_id: int | None = None, icon: str = "📁", color: str = "#6C63FF") -> Category:
        name = (name or "").strip()
        if not name:
            raise ValueError("نام دسته‌بندی نمی‌تواند خالی باشد.")
        self._check_unique(name, parent_id)
        with self.db.transaction() as conn:
            order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories").fetchone()[0]
            cur = conn.execute(
                "INSERT INTO categories(uuid, name, parent_id, icon, color, sort_order, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (str(uuidlib.uuid4()), name, parent_id, icon, color, order, now_iso()),
            )
            cid = cur.lastrowid
        return self.get(cid)

    def _check_unique(self, name: str, parent_id: int | None, exclude_id: int | None = None) -> None:
        row = self.db.query_one(
            "SELECT id FROM categories WHERE name = ? AND parent_id IS ? AND id IS NOT ?",
            (name, parent_id, exclude_id),
        )
        if row:
            raise ValueError("در همین سطح، دسته‌بندی دیگری با این نام وجود دارد.")

    def rename(self, category_id: int, name: str) -> None:
        name = (name or "").strip()
        if not name:
            raise ValueError("نام دسته‌بندی نمی‌تواند خالی باشد.")
        cat = self.get(category_id)
        if cat is None:
            raise KeyError("دسته‌بندی پیدا نشد.")
        self._check_unique(name, cat.parent_id, category_id)
        with self.db.transaction() as conn:
            conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
            self._reindex_subtree(conn, category_id)

    def set_style(self, category_id: int, icon: str | None = None, color: str | None = None) -> None:
        if icon is not None:
            self.db.execute("UPDATE categories SET icon = ? WHERE id = ?", (icon, category_id))
        if color is not None:
            self.db.execute("UPDATE categories SET color = ? WHERE id = ?", (color, category_id))

    def reparent(self, category_id: int, new_parent_id: int | None) -> None:
        if new_parent_id is not None and new_parent_id in self.descendant_ids(category_id):
            raise ValueError("یک دسته‌بندی را نمی‌توان داخل زیردسته‌ی خودش قرار داد.")
        cat = self.get(category_id)
        if cat is None:
            raise KeyError("دسته‌بندی پیدا نشد.")
        self._check_unique(cat.name, new_parent_id, category_id)
        with self.db.transaction() as conn:
            conn.execute("UPDATE categories SET parent_id = ? WHERE id = ?", (new_parent_id, category_id))
            self._reindex_subtree(conn, category_id)

    def delete(self, category_id: int, prompts_action: str = "uncategorize", target_id: int | None = None) -> None:
        """حذف دسته. prompts_action: uncategorize | move (به target_id) | trash.
        زیردسته‌ها به والد دسته‌ی حذف‌شده منتقل می‌شوند."""
        cat = self.get(category_id)
        if cat is None:
            raise KeyError("دسته‌بندی پیدا نشد.")
        if prompts_action == "move":
            if target_id is None or target_id == category_id:
                raise ValueError("دسته‌ی مقصد نامعتبر است.")
        elif prompts_action not in ("uncategorize", "trash"):
            raise ValueError("گزینه‌ی نامعتبر برای تعیین تکلیف پرامپت‌ها.")
        with self.db.transaction() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM prompts WHERE category_id = ?", (category_id,)).fetchall()]
            if prompts_action == "move":
                conn.execute("UPDATE prompts SET category_id = ? WHERE category_id = ?", (target_id, category_id))
            elif prompts_action == "trash":
                conn.execute(
                    "UPDATE prompts SET deleted_at = ?, category_id = NULL WHERE category_id = ?",
                    (now_iso(), category_id))
            else:
                conn.execute("UPDATE prompts SET category_id = NULL WHERE category_id = ?", (category_id,))
            conn.execute("UPDATE categories SET parent_id = ? WHERE parent_id = ?", (cat.parent_id, category_id))
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            for pid in ids:
                self._reindex_prompt(conn, pid)

    # ---------- داخلی ----------
    def _reindex_subtree(self, conn, category_id: int) -> None:
        ids, frontier = [category_id], [category_id]
        while frontier:
            marks = ",".join("?" * len(frontier))
            rows = conn.execute(f"SELECT id FROM categories WHERE parent_id IN ({marks})", frontier).fetchall()
            frontier = [r["id"] for r in rows if r["id"] not in ids]
            ids.extend(frontier)
        marks = ",".join("?" * len(ids))
        for r in conn.execute(f"SELECT id FROM prompts WHERE category_id IN ({marks})", ids).fetchall():
            self._reindex_prompt(conn, r["id"])

    @staticmethod
    def _reindex_prompt(conn, prompt_id: int) -> None:
        from .prompt_service import PromptService  # جلوگیری از وابستگی حلقوی در زمان import
        PromptService._reindex(PromptService.__new__(PromptService), conn, prompt_id)
