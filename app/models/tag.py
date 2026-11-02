"""مدل برچسب."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tag:
    id: int
    name: str
    count: int = 0
