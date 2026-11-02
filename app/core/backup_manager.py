"""بکاپ دستی و خودکار با راستی‌آزمایی، چرخش نسخه‌ها و بکاپ ایمنی پیش از بازیابی."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..utils.paths import now_iso
from .export_manager import ExportManager
from .import_manager import PVaultError, load_package
from .settings import Settings

EXT = ".pvault"
PREFIX = "PromptVault_"
SAFETY_PREFIX = "PromptVault_pre-restore_"


@dataclass
class BackupInfo:
    path: Path
    size: int
    modified: datetime
    is_safety: bool


class BackupManager:
    def __init__(self, exporter: ExportManager, settings: Settings, data_dir: str | Path):
        self.exporter = exporter
        self.settings = settings
        self.data_dir = Path(data_dir)

    # ---------- مسیرها ----------
    def default_dir(self) -> Path:
        return self.data_dir / "backups"

    def backup_dir(self) -> Path:
        custom = (self.settings.get("backup_dir") or "").strip()
        return Path(custom) if custom else self.default_dir()

    def safety_dir(self) -> Path:
        return self.data_dir / "safety_backups"

    # ---------- ساخت ----------
    def create_backup(self, dest_dir: str | Path | None = None, *, auto: bool = False) -> Path:
        """بکاپ کامل .pvault می‌سازد و بلافاصله صحت آن را بررسی می‌کند. اگر معتبر نبود حذفش می‌کند."""
        folder = Path(dest_dir) if dest_dir else self.backup_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = self._unique_path(folder, PREFIX + datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.exporter.export_pvault(path)
        try:
            self.verify(path)
        except PVaultError:
            path.unlink(missing_ok=True)
            raise
        self.settings.set("data_changed_since_backup", False)
        if auto:
            self.settings.set("last_auto_backup", now_iso())
        return path

    def create_safety_backup(self, dest_dir: str | Path | None = None) -> Path:
        """بکاپ ایمنی پیش از بازیابی/ادغام؛ تا اگر چیزی خراب شد بتوان به وضعیت قبل برگشت."""
        folder = Path(dest_dir) if dest_dir else self.safety_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = self._unique_path(folder, SAFETY_PREFIX + datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.exporter.export_pvault(path)
        self.verify(path)
        self._rotate(folder, SAFETY_PREFIX, keep=5)
        return path

    @staticmethod
    def _unique_path(folder: Path, stem: str) -> Path:
        p = folder / f"{stem}{EXT}"
        i = 1
        while p.exists():
            p = folder / f"{stem}_{i}{EXT}"
            i += 1
        return p

    # ---------- راستی‌آزمایی ----------
    def verify(self, path: str | Path) -> dict:
        """فایل را به‌طور کامل می‌خواند و می‌سنجد؛ در صورت مشکل PVaultError با پیام فارسی."""
        pkg = load_package(path)
        counts = pkg.manifest.get("counts", {})
        for key in ("prompts", "categories", "templates"):
            if key in counts and counts[key] != len(pkg.data.get(key, [])):
                raise PVaultError("تعداد موارد ثبت‌شده در بکاپ با محتوای آن یکسان نیست؛ بکاپ ناقص است.")
        return pkg.manifest

    # ---------- فهرست و چرخش ----------
    def list_backups(self, folder: str | Path | None = None) -> list[BackupInfo]:
        folder = Path(folder) if folder else self.backup_dir()
        if not folder.is_dir():
            return []
        out = []
        for f in folder.glob(f"*{EXT}"):
            st = f.stat()
            out.append(BackupInfo(f, st.st_size, datetime.fromtimestamp(st.st_mtime), f.name.startswith(SAFETY_PREFIX)))
        out.sort(key=lambda b: b.modified, reverse=True)
        return out

    def _rotate(self, folder: Path, prefix: str, keep: int) -> list[Path]:
        files = sorted(
            (f for f in folder.glob(f"{prefix}*{EXT}") if prefix == SAFETY_PREFIX or not f.name.startswith(SAFETY_PREFIX)),
            key=lambda f: f.stat().st_mtime, reverse=True)
        removed = []
        for f in files[max(keep, 1):]:
            try:
                f.unlink()
                removed.append(f)
            except OSError:
                pass
        return removed

    def rotate(self) -> list[Path]:
        """بکاپ‌های قدیمی‌تر از تعداد تنظیم‌شده را حذف می‌کند (بکاپ‌های ایمنی جدا مدیریت می‌شوند)."""
        keep = int(self.settings.get("backup_keep") or 10)
        return self._rotate(self.backup_dir(), PREFIX, keep)

    def delete_backup(self, path: str | Path) -> None:
        p = Path(path)
        if p.suffix.lower() == EXT and p.is_file():
            p.unlink()

    # ---------- خودکار ----------
    def due(self, now: datetime | None = None) -> bool:
        """آیا طبق زمان‌بندی (روزانه/هفتگی) الان وقت بکاپ خودکار است؟"""
        if not self.settings.get("backup_auto_enabled"):
            return False
        schedule = self.settings.get("backup_schedule")
        if schedule not in ("daily", "weekly"):
            return False
        last = self.settings.get("last_auto_backup")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
        except ValueError:
            return True
        delta = timedelta(days=1 if schedule == "daily" else 7)
        return (now or datetime.now()) - last_dt >= delta

    def run_if_due(self) -> Path | None:
        if self.due():
            return self._auto()
        return None

    def run_on_exit(self) -> Path | None:
        """هنگام بستن برنامه: بسته به تنظیم، همیشه یا فقط در صورت وجود تغییر بکاپ می‌گیرد."""
        if not self.settings.get("backup_auto_enabled"):
            return None
        schedule = self.settings.get("backup_schedule")
        if schedule == "on_exit":
            return self._auto()
        if schedule == "on_exit_if_changed" and self.settings.get("data_changed_since_backup"):
            return self._auto()
        return None

    def _auto(self) -> Path:
        path = self.create_backup(auto=True)
        self.rotate()
        return path
