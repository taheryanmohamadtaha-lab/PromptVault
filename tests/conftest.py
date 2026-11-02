import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.context import AppContext  # noqa: E402


@pytest.fixture()
def ctx(tmp_path):
    c = AppContext(tmp_path / "data")
    yield c
    c.close()


@pytest.fixture()
def ctx2(tmp_path):
    """یک نصب تازه‌ی دیگر (شبیه‌سازی کامپیوتر دوم)."""
    c = AppContext(tmp_path / "other_pc" / "data")
    yield c
    c.close()
