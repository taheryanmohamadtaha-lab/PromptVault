"""خروجی گرفتن: JSON، بسته‌ی کامل .pvault، CSV، Markdown و TXT."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from .. import __version__
from ..utils.paths import now_iso
from .database import Database
from .settings import Settings

FORMAT_NAME = "PVault"
FORMAT_VERSION = 1
ALL_PARTS = ("categories", "tags", "prompts", "versions", "templates", "attachments", "settings")
# تنظیماتی که وابسته به همین کامپیوتر هستند و منتقل نمی‌شوند
MACHINE_SETTINGS = {"backup_dir", "last_auto_backup", "data_changed_since_backup", "update_url"}


class ExportManager:
    def __init__(self, db: Database, settings: Settings, attachments_dir: str | Path):
        self.db = db
        self.settings = settings
        self.attachments_dir = Path(attachments_dir)

    # ---------- ساخت ساختار داده ----------
    def build_data(self, parts: Iterable[str] = ALL_PARTS) -> dict:
        parts = set(parts)
        unknown = parts - set(ALL_PARTS)
        if unknown:
            raise ValueError(f"بخش نامعتبر برای خروجی: {', '.join(sorted(unknown))}")
        q = self.db.query
        data: dict = {}

        cat_uuid = {r["id"]: r["uuid"] for r in q("SELECT id, uuid FROM categories")}
        if "categories" in parts or "prompts" in parts or "templates" in parts:
            data["categories"] = [
                {"uuid": r["uuid"], "name": r["name"], "parent_uuid": cat_uuid.get(r["parent_id"]),
                 "icon": r["icon"], "color": r["color"], "sort_order": r["sort_order"],
                 "created_at": r["created_at"]}
                for r in q("SELECT * FROM categories ORDER BY sort_order, id")
            ]
        if "tags" in parts:
            data["tags"] = [r["name"] for r in q("SELECT name FROM tags ORDER BY name COLLATE NOCASE")]

        if "prompts" in parts:
            tags_by_prompt: dict[int, list[str]] = {}
            for r in q("SELECT pt.prompt_id, t.name FROM prompt_tags pt JOIN tags t ON t.id = pt.tag_id "
                       "ORDER BY t.name COLLATE NOCASE"):
                tags_by_prompt.setdefault(r["prompt_id"], []).append(r["name"])
            versions_by_prompt: dict[int, list[dict]] = {}
            if "versions" in parts:
                for r in q("SELECT * FROM versions ORDER BY prompt_id, version_no"):
                    versions_by_prompt.setdefault(r["prompt_id"], []).append({
                        "version_no": r["version_no"], "title": r["title"], "body": r["body"],
                        "note": r["note"], "created_at": r["created_at"]})
            atts_by_prompt: dict[int, list[dict]] = {}
            if "attachments" in parts:
                for r in q("SELECT * FROM attachments ORDER BY prompt_id, id"):
                    atts_by_prompt.setdefault(r["prompt_id"], []).append({
                        "filename": r["filename"], "stored_name": r["stored_name"],
                        "size": r["size"], "sha256": r["sha256"], "created_at": r["created_at"]})
            data["prompts"] = []
            for r in q("SELECT * FROM prompts ORDER BY id"):
                item = {
                    "uuid": r["uuid"], "title": r["title"], "body": r["body"],
                    "category_uuid": cat_uuid.get(r["category_id"]), "platform": r["platform"],
                    "output_type": r["output_type"], "notes": r["notes"], "status": r["status"],
                    "importance": r["importance"], "favorite": bool(r["favorite"]),
                    "pinned": bool(r["pinned"]), "archived": bool(r["archived"]),
                    "deleted_at": r["deleted_at"], "use_count": r["use_count"],
                    "last_used_at": r["last_used_at"], "created_at": r["created_at"],
                    "updated_at": r["updated_at"], "tags": tags_by_prompt.get(r["id"], []),
                }
                if "versions" in parts:
                    item["versions"] = versions_by_prompt.get(r["id"], [])
                if "attachments" in parts:
                    item["attachments"] = atts_by_prompt.get(r["id"], [])
                data["prompts"].append(item)

        if "templates" in parts:
            data["templates"] = [
                {"uuid": r["uuid"], "title": r["title"], "body": r["body"],
                 "description": r["description"], "category_uuid": cat_uuid.get(r["category_id"]),
                 "created_at": r["created_at"], "updated_at": r["updated_at"]}
                for r in q("SELECT * FROM templates ORDER BY id")
            ]
        if "settings" in parts:
            data["settings"] = {k: v for k, v in self.settings.all().items() if k not in MACHINE_SETTINGS}
        return data

    def _envelope(self, data: dict, extra: dict | None = None) -> dict:
        env = {
            "format": FORMAT_NAME, "format_version": FORMAT_VERSION,
            "app_version": __version__, "created_at": now_iso(), **(extra or {}),
        }
        env["counts"] = {k: (len(v) if isinstance(v, (list, dict)) else 0) for k, v in data.items()}
        return env

    # ---------- JSON ----------
    def export_json(self, dest: str | Path, parts: Iterable[str] = ALL_PARTS) -> Path:
        data = self.build_data(parts)
        doc = {**self._envelope(data), "data": data}
        return self._atomic_write_text(Path(dest), json.dumps(doc, ensure_ascii=False, indent=2))

    # ---------- بسته‌ی کامل .pvault ----------
    def export_pvault(self, dest: str | Path) -> Path:
        dest = Path(dest)
        data = self.build_data(ALL_PARTS)
        data_bytes = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
        files: list[dict] = []
        used: set[str] = set()
        for p in data["prompts"]:
            for a in p.get("attachments", []):
                used.add(a["stored_name"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".pvault.tmp", dir=str(dest.parent))
        os.close(tmp_fd)
        try:
            with zipfile.ZipFile(tmp_name, "w", zipfile.ZIP_DEFLATED) as zf:
                for name in sorted(used):
                    fp = self.attachments_dir / name
                    if not fp.is_file():
                        continue  # پیوست گم‌شده؛ در manifest ثبت نمی‌شود و هنگام وارد کردن «بدون فایل» علامت می‌خورد
                    h = hashlib.sha256()
                    with open(fp, "rb") as f:
                        for chunk in iter(lambda: f.read(1024 * 1024), b""):
                            h.update(chunk)
                    files.append({"name": f"attachments/{name}", "sha256": h.hexdigest(), "size": fp.stat().st_size})
                    zf.write(fp, f"attachments/{name}")
                manifest = {
                    **self._envelope(data),
                    "data_sha256": hashlib.sha256(data_bytes).hexdigest(),
                    "files": files,
                }
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                zf.writestr("data.json", data_bytes)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp_name, dest)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return dest

    # ---------- CSV / Markdown / TXT ----------
    def export_csv(self, dest: str | Path) -> Path:
        data = self.build_data(("categories", "prompts", "tags"))
        cats = {c["uuid"]: c for c in data["categories"]}

        def path_of(uid: str | None) -> str:
            names, guard = [], 0
            while uid and uid in cats and guard < 20:
                names.append(cats[uid]["name"])
                uid = cats[uid]["parent_uuid"]
                guard += 1
            return " > ".join(reversed(names))

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8-sig", newline="") as f:  # BOM برای باز شدن درست فارسی در Excel
            w = csv.writer(f)
            w.writerow(["عنوان", "دسته‌بندی", "برچسب‌ها", "پلتفرم", "نوع خروجی", "وضعیت", "اهمیت",
                        "علاقه‌مندی", "تعداد استفاده", "تاریخ ایجاد", "آخرین ویرایش", "توضیحات", "متن پرامپت"])
            for p in data["prompts"]:
                if p["deleted_at"]:
                    continue
                w.writerow([p["title"], path_of(p["category_uuid"]), "، ".join(p["tags"]), p["platform"],
                            p["output_type"], p["status"], p["importance"], "بله" if p["favorite"] else "خیر",
                            p["use_count"], p["created_at"], p["updated_at"], p["notes"], p["body"]])
        return dest

    def export_markdown(self, dest: str | Path) -> Path:
        return self._export_text(Path(dest), markdown=True)

    def export_txt(self, dest: str | Path) -> Path:
        return self._export_text(Path(dest), markdown=False)

    def _export_text(self, dest: Path, markdown: bool) -> Path:
        data = self.build_data(("categories", "prompts"))
        cats = {c["uuid"]: c["name"] for c in data["categories"]}
        lines: list[str] = []
        for p in data["prompts"]:
            if p["deleted_at"]:
                continue
            cat = cats.get(p["category_uuid"], "بدون دسته‌بندی")
            if markdown:
                lines.append(f"## {p['title']}\n")
                meta = [f"دسته‌بندی: {cat}"]
                if p["platform"]:
                    meta.append(f"پلتفرم: {p['platform']}")
                if p["tags"]:
                    meta.append("برچسب‌ها: " + "، ".join(p["tags"]))
                lines.append("> " + " | ".join(meta) + "\n")
                lines.append(p["body"] + "\n\n---\n")
            else:
                lines.append(f"{p['title']}\nدسته‌بندی: {cat}\n{'-' * 40}\n{p['body']}\n\n{'=' * 60}\n")
        return self._atomic_write_text(dest, "\n".join(lines))

    @staticmethod
    def _atomic_write_text(dest: Path, text: str) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, dest)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return dest
