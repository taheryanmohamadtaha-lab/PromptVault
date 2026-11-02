"""مدل قالب پرامپت."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Template:
    id: int
    uuid: str
    title: str
    body: str
    description: str
    category_id: int | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Template":
        return cls(
            id=row["id"], uuid=row["uuid"], title=row["title"], body=row["body"],
            description=row["description"], category_id=row["category_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
