"""مدل پیوست."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Attachment:
    id: int
    prompt_id: int
    filename: str
    stored_name: str
    size: int
    sha256: str
    created_at: str
    kind: str = "file"      # file | image | result

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Attachment":
        return cls(
            id=row["id"], prompt_id=row["prompt_id"], filename=row["filename"],
            stored_name=row["stored_name"], size=row["size"], sha256=row["sha256"],
            created_at=row["created_at"], kind=row["kind"],
        )
