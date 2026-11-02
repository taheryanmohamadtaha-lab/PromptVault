"""مدل پرامپت."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

STATUSES = ["فعال", "پیش‌نویس", "آزمایشی", "منسوخ"]
IMPORTANCE_LABELS = {1: "کم", 2: "متوسط", 3: "زیاد", 4: "حیاتی"}


@dataclass
class Prompt:
    id: int
    uuid: str
    title: str
    body: str
    category_id: int | None
    platform: str
    output_type: str
    notes: str
    status: str
    importance: int
    favorite: bool
    pinned: bool
    archived: bool
    deleted_at: str | None
    use_count: int
    last_used_at: str | None
    created_at: str
    updated_at: str
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: sqlite3.Row, tags: list[str] | None = None) -> "Prompt":
        return cls(
            id=row["id"], uuid=row["uuid"], title=row["title"], body=row["body"],
            category_id=row["category_id"], platform=row["platform"],
            output_type=row["output_type"], notes=row["notes"], status=row["status"],
            importance=row["importance"], favorite=bool(row["favorite"]),
            pinned=bool(row["pinned"]), archived=bool(row["archived"]),
            deleted_at=row["deleted_at"], use_count=row["use_count"],
            last_used_at=row["last_used_at"], created_at=row["created_at"],
            updated_at=row["updated_at"], tags=list(tags or []),
        )
