"""مدل دسته‌بندی."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class Category:
    id: int
    uuid: str
    name: str
    parent_id: int | None
    icon: str
    color: str
    sort_order: int
    created_at: str
    count: int = 0
    children: list["Category"] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: sqlite3.Row, count: int = 0) -> "Category":
        return cls(
            id=row["id"], uuid=row["uuid"], name=row["name"], parent_id=row["parent_id"],
            icon=row["icon"], color=row["color"], sort_order=row["sort_order"],
            created_at=row["created_at"], count=count,
        )
