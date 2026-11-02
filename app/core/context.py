"""AppContext: همه‌ی سرویس‌ها را یک‌جا می‌سازد و به هم وصل می‌کند (بدون وابستگی به Qt)."""
from __future__ import annotations

from pathlib import Path

from ..services.category_service import CategoryService
from ..services.file_service import FileService
from ..services.prompt_service import PromptService
from ..services.search_service import SearchService
from ..services.tag_service import TagService
from ..services.template_service import TemplateService
from ..services.version_service import VersionService
from ..utils.paths import get_data_dir
from .backup_manager import BackupManager
from .database import Database
from .export_manager import ExportManager
from .import_manager import ImportManager
from .settings import Settings


class AppContext:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "promptvault.db")
        self.settings = Settings(self.db)
        self.attachments_dir = self.data_dir / "attachments"

        self.prompts = PromptService(self.db)
        self.categories = CategoryService(self.db)
        self.tags = TagService(self.db)
        self.search = SearchService(self.db, self.prompts, self.categories)
        self.versions = VersionService(self.db, self.prompts)
        self.templates = TemplateService(self.db)
        self.files = FileService(self.db, self.attachments_dir)

        self.exporter = ExportManager(self.db, self.settings, self.attachments_dir)
        self.backups = BackupManager(self.exporter, self.settings, self.data_dir)
        self.importer = ImportManager(
            self.db, self.settings, self.prompts, self.templates, self.files, self.backups)

        self.categories.seed_defaults()
        self.templates.seed_defaults()

    def close(self) -> None:
        self.db.close()
