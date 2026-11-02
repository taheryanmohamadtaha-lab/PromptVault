"""جست‌وجو و فیلتر پرامپت‌ها (کاملاً محلی، با نرمال‌سازی فارسی)."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.database import Database
from ..models.prompt import Prompt
from ..utils.text import normalize
from .category_service import CategoryService
from .prompt_service import PromptService

SORTS = {
    "updated": "p.updated_at DESC",
    "created": "p.created_at DESC",
    "title": "p.title COLLATE NOCASE ASC",
    "used": "p.last_used_at DESC",
    "use_count": "p.use_count DESC",
    "importance": "p.importance DESC, p.updated_at DESC",
}


@dataclass
class PromptFilter:
    query: str = ""
    category_id: int | None = None          # شامل زیردسته‌ها
    uncategorized: bool = False
    tag: str = ""
    platform: str = ""
    favorite_only: bool = False
    pinned_only: bool = False
    min_importance: int = 0
    used: bool | None = None                # True: استفاده‌شده، False: استفاده‌نشده
    created_from: str = ""                  # YYYY-MM-DD
    created_to: str = ""
    updated_from: str = ""
    updated_to: str = ""
    status: str = ""
    view: str = "active"                    # active | archived | trash | all
    sort: str = "updated"
    limit: int = 0


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SearchService:
    def __init__(self, db: Database, prompts: PromptService, categories: CategoryService):
        self.db = db
        self.prompts = prompts
        self.categories = categories

    def search(self, f: PromptFilter | None = None) -> list[Prompt]:
        f = f or PromptFilter()
        where: list[str] = []
        params: list = []

        if f.view == "active":
            where.append("p.deleted_at IS NULL AND p.archived = 0")
        elif f.view == "archived":
            where.append("p.deleted_at IS NULL AND p.archived = 1")
        elif f.view == "trash":
            where.append("p.deleted_at IS NOT NULL")
        elif f.view == "all":
            where.append("p.deleted_at IS NULL")

        for word in [w for w in normalize(f.query).split(" ") if w]:
            where.append("p.search_text LIKE ? ESCAPE '\\'")
            params.append(f"%{_like_escape(word)}%")

        if f.uncategorized:
            where.append("p.category_id IS NULL")
        elif f.category_id is not None:
            ids = self.categories.descendant_ids(f.category_id)
            where.append(f"p.category_id IN ({','.join('?' * len(ids))})")
            params.extend(ids)

        if f.tag:
            where.append(
                "EXISTS (SELECT 1 FROM prompt_tags pt JOIN tags t ON t.id = pt.tag_id "
                "WHERE pt.prompt_id = p.id AND t.name = ? COLLATE NOCASE)")
            params.append(f.tag.strip().lstrip("#"))
        if f.platform:
            where.append("p.platform = ? COLLATE NOCASE")
            params.append(f.platform.strip())
        if f.status:
            where.append("p.status = ?")
            params.append(f.status)
        if f.favorite_only:
            where.append("p.favorite = 1")
        if f.pinned_only:
            where.append("p.pinned = 1")
        if f.min_importance:
            where.append("p.importance >= ?")
            params.append(f.min_importance)
        if f.used is True:
            where.append("p.use_count > 0")
        elif f.used is False:
            where.append("p.use_count = 0")
        if f.created_from:
            where.append("substr(p.created_at, 1, 10) >= ?")
            params.append(f.created_from)
        if f.created_to:
            where.append("substr(p.created_at, 1, 10) <= ?")
            params.append(f.created_to)
        if f.updated_from:
            where.append("substr(p.updated_at, 1, 10) >= ?")
            params.append(f.updated_from)
        if f.updated_to:
            where.append("substr(p.updated_at, 1, 10) <= ?")
            params.append(f.updated_to)

        order = SORTS.get(f.sort, SORTS["updated"])
        sql = "SELECT p.* FROM prompts p"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY p.pinned DESC, {order}, p.id DESC"
        if f.limit:
            sql += f" LIMIT {int(f.limit)}"
        return self.prompts.hydrate(self.db.query(sql, params))

    # ---------- فهرست‌های آماده برای داشبورد ----------
    def recent_added(self, limit: int = 6) -> list[Prompt]:
        return self.search(PromptFilter(sort="created", limit=limit))

    def recent_edited(self, limit: int = 6) -> list[Prompt]:
        return self.search(PromptFilter(sort="updated", limit=limit))

    def recent_used(self, limit: int = 6) -> list[Prompt]:
        rows = self.db.query(
            "SELECT * FROM prompts WHERE deleted_at IS NULL AND last_used_at IS NOT NULL "
            "ORDER BY last_used_at DESC LIMIT ?", (limit,))
        return self.prompts.hydrate(rows)

    def important(self, limit: int = 6) -> list[Prompt]:
        rows = self.db.query(
            "SELECT * FROM prompts WHERE deleted_at IS NULL AND archived = 0 "
            "AND (pinned = 1 OR importance >= 3) ORDER BY pinned DESC, importance DESC, updated_at DESC LIMIT ?",
            (limit,))
        return self.prompts.hydrate(rows)

    def platforms(self) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT platform FROM prompts WHERE platform != '' AND deleted_at IS NULL "
            "ORDER BY platform COLLATE NOCASE")
        return [r["platform"] for r in rows]
