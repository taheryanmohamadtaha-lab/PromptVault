"""وارد کردن/بازیابی: اعتبارسنجی بسته، پیش‌نمایش، تشخیص موارد تکراری و ادغام امن.

نکات امنیتی:
- هیچ فایلی از داخل ZIP روی دیسک «استخراج» نمی‌شود؛ بایت‌ها در حافظه خوانده و با SHA-256 تأیید می‌شوند،
  پس حمله‌ی Zip Slip ممکن نیست. نام اعضا هم به‌صورت جداگانه اعتبارسنجی می‌شود.
- سقف تعداد اعضا، حجم کل و نسبت فشرده‌سازی (ZIP bomb) بررسی می‌شود.
- همه‌ی تغییرات دیتابیس در یک تراکنش اتمی انجام می‌شود؛ با خطا، چیزی تغییر نمی‌کند.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid as uuidlib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..utils.paths import now_iso
from ..utils.text import normalize
from .database import Database
from .export_manager import FORMAT_NAME, FORMAT_VERSION, MACHINE_SETTINGS
from .settings import Settings

MAX_MEMBERS = 20000
MAX_TOTAL_BYTES = 2 * 1024 ** 3
MAX_RATIO = 1000
_SAFE_ATT = re.compile(r"^attachments/[A-Za-z0-9._-]{1,200}$")


class PVaultError(Exception):
    """خطای قابل‌نمایش به کاربر (فارسی)."""


@dataclass
class Package:
    path: Path
    kind: str                       # pvault | json
    manifest: dict
    data: dict
    zip_path: Path | None = None
    attachment_names: set[str] = field(default_factory=set)

    def read_attachment(self, stored_name: str) -> bytes | None:
        if self.zip_path is None:
            return None
        member = f"attachments/{stored_name}"
        if member not in self.attachment_names:
            return None
        with zipfile.ZipFile(self.zip_path) as zf:
            return zf.read(member)


def load_package(path: str | Path) -> Package:
    """فایل .pvault یا .json را با اعتبارسنجی کامل می‌خواند. در صورت مشکل PVaultError با پیام فارسی."""
    path = Path(path)
    if not path.is_file():
        raise PVaultError("فایل انتخاب‌شده پیدا نشد.")
    if path.suffix.lower() == ".json":
        return _load_json(path)
    return _load_pvault(path)


def _check_envelope(doc: dict) -> None:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT_NAME:
        raise PVaultError("این فایل، بکاپ گنجینه پرامپت نیست یا ساختار آن نامعتبر است.")
    ver = doc.get("format_version")
    if not isinstance(ver, int) or ver > FORMAT_VERSION:
        raise PVaultError("این بکاپ با نسخه‌ی جدیدتری از برنامه ساخته شده است. لطفاً برنامه را به‌روزرسانی کنید.")


def _load_json(path: Path) -> Package:
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise PVaultError(f"فایل JSON خوانده نشد یا خراب است: {e}") from e
    _check_envelope(doc)
    data = doc.get("data")
    if not isinstance(data, dict):
        raise PVaultError("بخش «data» در فایل JSON وجود ندارد.")
    _validate_data(data)
    manifest = {k: v for k, v in doc.items() if k != "data"}
    return Package(path, "json", manifest, data)


def _load_pvault(path: Path) -> Package:
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise PVaultError("فایل بکاپ خراب است یا فرمت ZIP معتبر ندارد.") from e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise PVaultError("تعداد فایل‌های داخل بکاپ بیش از حد مجاز است.")
        total = 0
        names: set[str] = set()
        for info in infos:
            n = info.filename
            if n.startswith("/") or "\\" in n or ".." in n.split("/") or ":" in n or "\x00" in n:
                raise PVaultError(f"بکاپ شامل مسیر ناامن است و رد شد: «{n}»")
            if info.is_dir():
                continue
            if n not in ("manifest.json", "data.json") and not _SAFE_ATT.match(n):
                raise PVaultError(f"بکاپ شامل فایل غیرمجاز است و رد شد: «{n}»")
            if n in names:
                raise PVaultError("بکاپ شامل نام تکراری است و رد شد.")
            names.add(n)
            total += info.file_size
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 10 * 1024 ** 2:
                raise PVaultError("نسبت فشرده‌سازی بکاپ مشکوک است و رد شد.")
        if total > MAX_TOTAL_BYTES:
            raise PVaultError("حجم بکاپ بیش از حد مجاز است.")
        if "manifest.json" not in names or "data.json" not in names:
            raise PVaultError("بکاپ ناقص است (manifest.json یا data.json وجود ندارد).")
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            data_bytes = zf.read("data.json")
            data = json.loads(data_bytes.decode("utf-8"))
        except (ValueError, zipfile.BadZipFile, UnicodeDecodeError) as e:
            raise PVaultError("محتوای بکاپ خوانده نشد یا خراب است.") from e
        _check_envelope(manifest)
        if manifest.get("data_sha256") != hashlib.sha256(data_bytes).hexdigest():
            raise PVaultError("بررسی صحت ناموفق بود: اطلاعات بکاپ تغییر کرده یا خراب است.")
        listed = {f["name"]: f for f in manifest.get("files", []) if isinstance(f, dict) and "name" in f}
        for name, meta in listed.items():
            if name not in names:
                raise PVaultError(f"فایل پیوست در بکاپ وجود ندارد: «{name}»")
            h = hashlib.sha256()
            with zf.open(name) as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != meta.get("sha256"):
                raise PVaultError(f"بررسی صحت ناموفق بود: پیوست خراب است («{name}»).")
        stray = {n for n in names if n.startswith("attachments/")} - set(listed)
        if stray:
            raise PVaultError("بکاپ شامل پیوست‌هایی است که در فهرست ثبت نشده‌اند و رد شد.")
        _validate_data(data)
        att_names = {n for n in names if n.startswith("attachments/")}
    return Package(path, "pvault", manifest, data, zip_path=path, attachment_names=att_names)


def _validate_data(data: dict) -> None:
    for key in ("categories", "prompts", "templates"):
        if key in data and not isinstance(data[key], list):
            raise PVaultError(f"ساختار بخش «{key}» نامعتبر است.")
    for p in data.get("prompts", []):
        if not isinstance(p, dict) or not isinstance(p.get("title"), str) or not p["title"].strip():
            raise PVaultError("یکی از پرامپت‌ها عنوان معتبر ندارد؛ فایل رد شد.")
        if not isinstance(p.get("uuid"), str) or not p["uuid"]:
            raise PVaultError("یکی از پرامپت‌ها شناسه ندارد؛ فایل رد شد.")
        if not isinstance(p.get("body", ""), str):
            raise PVaultError("متن یکی از پرامپت‌ها نامعتبر است؛ فایل رد شد.")
        if not isinstance(p.get("tags", []), list):
            raise PVaultError("برچسب‌های یکی از پرامپت‌ها نامعتبر است؛ فایل رد شد.")
    for c in data.get("categories", []):
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not isinstance(c.get("uuid"), str):
            raise PVaultError("یکی از دسته‌بندی‌ها نامعتبر است؛ فایل رد شد.")
    for t in data.get("templates", []):
        if not isinstance(t, dict) or not isinstance(t.get("title"), str) or not isinstance(t.get("uuid"), str):
            raise PVaultError("یکی از قالب‌ها نامعتبر است؛ فایل رد شد.")


# ---------------------------------------------------------------------------
# پیش‌نمایش و اعمال
# ---------------------------------------------------------------------------
NEW, IDENTICAL, CHANGED, SIMILAR = "new", "identical", "changed", "similar"
SKIP, REPLACE, BOTH = "skip", "replace", "both"


@dataclass
class PreviewItem:
    kind: str                # prompt | template
    uuid: str
    title: str
    status: str              # new | identical | changed | similar
    existing_id: int | None = None
    existing_title: str = ""
    reason: str = ""


@dataclass
class Preview:
    items: list[PreviewItem]
    counts: dict[str, int]
    categories_new: int
    tags_new: int
    settings_included: bool

    @property
    def conflicts(self) -> list[PreviewItem]:
        return [i for i in self.items if i.status in (CHANGED, SIMILAR)]


@dataclass
class ImportResult:
    added: int = 0
    replaced: int = 0
    skipped: int = 0
    duplicated: int = 0
    templates_added: int = 0
    templates_replaced: int = 0
    categories_added: int = 0
    attachments_added: int = 0
    attachments_missing: int = 0
    safety_backup: str = ""


def _same_content(existing: dict, incoming: dict) -> bool:
    return existing["title"] == incoming["title"] and existing["body"] == incoming.get("body", "")


class ImportManager:
    def __init__(self, db: Database, settings: Settings, prompts, templates, files, backups):
        self.db = db
        self.settings = settings
        self.prompts = prompts
        self.templates = templates
        self.files = files
        self.backups = backups

    # ---------- پیش‌نمایش ----------
    def preview(self, pkg: Package) -> Preview:
        items: list[PreviewItem] = []
        by_uuid = {r["uuid"]: r for r in self.db.query("SELECT id, uuid, title, body FROM prompts")}
        by_title: dict[str, list] = {}
        by_body: dict[str, list] = {}
        for r in by_uuid.values():
            by_title.setdefault(r["title"].strip(), []).append(r)
            if r["body"].strip():
                by_body.setdefault(normalize(r["body"]), []).append(r)
        for p in pkg.data.get("prompts", []):
            body = p.get("body", "")
            ex = by_uuid.get(p["uuid"])
            if ex is not None:
                st = IDENTICAL if _same_content(ex, p) else CHANGED
                items.append(PreviewItem("prompt", p["uuid"], p["title"], st, ex["id"], ex["title"],
                                         "همین پرامپت از قبل وجود دارد" + ("" if st == IDENTICAL else " ولی محتوا تفاوت دارد")))
                continue
            sim = None
            reason = ""
            for r in by_title.get(p["title"].strip(), []):
                sim, reason = r, "عنوان یکسان"
                break
            if sim is None and body.strip():
                for r in by_body.get(normalize(body), []):
                    sim, reason = r, "متن یکسان با عنوان متفاوت"
                    break
            if sim is not None:
                items.append(PreviewItem("prompt", p["uuid"], p["title"], SIMILAR, sim["id"], sim["title"], reason))
            else:
                items.append(PreviewItem("prompt", p["uuid"], p["title"], NEW))

        t_by_uuid = {r["uuid"]: r for r in self.db.query("SELECT * FROM templates")}
        t_by_title = {r["title"].strip(): r for r in t_by_uuid.values()}
        for t in pkg.data.get("templates", []):
            ex = t_by_uuid.get(t["uuid"])
            if ex is not None:
                same = ex["title"] == t["title"] and ex["body"] == t.get("body", "")
                items.append(PreviewItem("template", t["uuid"], t["title"], IDENTICAL if same else CHANGED,
                                         ex["id"], ex["title"]))
            elif t["title"].strip() in t_by_title:
                ex = t_by_title[t["title"].strip()]
                items.append(PreviewItem("template", t["uuid"], t["title"], SIMILAR, ex["id"], ex["title"], "عنوان یکسان"))
            else:
                items.append(PreviewItem("template", t["uuid"], t["title"], NEW))

        have_cats = {r["uuid"] for r in self.db.query("SELECT uuid FROM categories")}
        cats_new = sum(1 for c in pkg.data.get("categories", []) if c["uuid"] not in have_cats)
        have_tags = {normalize(r["name"]) for r in self.db.query("SELECT name FROM tags")}
        incoming_tags = set(pkg.data.get("tags", []))
        for p in pkg.data.get("prompts", []):
            incoming_tags.update(p.get("tags", []))
        tags_new = sum(1 for t in incoming_tags if normalize(t) not in have_tags)
        counts = {s: sum(1 for i in items if i.status == s) for s in (NEW, IDENTICAL, CHANGED, SIMILAR)}
        counts["prompts"] = len(pkg.data.get("prompts", []))
        counts["templates"] = len(pkg.data.get("templates", []))
        return Preview(items, counts, cats_new, tags_new, bool(pkg.data.get("settings")))

    # ---------- اعمال ----------
    def apply(
        self,
        pkg: Package,
        *,
        mode: str = "merge",                       # merge | replace_all
        default_action: str = SKIP,                # برای موارد changed/similar
        decisions: dict[str, str] | None = None,   # uuid -> skip|replace|both
        import_settings: bool = False,
        safety_dir: str | Path | None = None,
    ) -> ImportResult:
        if mode not in ("merge", "replace_all"):
            raise ValueError("حالت بازیابی نامعتبر است.")
        decisions = decisions or {}
        result = ImportResult()
        # ۱) قبل از هر تغییر، از وضعیت فعلی بکاپ ایمنی بگیر
        if self._has_data():
            result.safety_backup = str(self.backups.create_safety_backup(safety_dir))

        written_files: list[Path] = []
        old_files: list[Path] = []
        try:
            with self.db.transaction() as conn:
                if mode == "replace_all":
                    old_files = [self.files.dir / r["stored_name"] for r in conn.execute(
                        "SELECT stored_name FROM attachments").fetchall()]
                    for tbl in ("prompts", "templates", "categories", "tags"):
                        conn.execute(f"DELETE FROM {tbl}")
                cat_map = self._import_categories(conn, pkg, result)
                self._import_templates(conn, pkg, cat_map, mode, default_action, decisions, result)
                self._import_prompts(conn, pkg, cat_map, mode, default_action, decisions, result, written_files)
                if import_settings and pkg.data.get("settings"):
                    clean = {k: v for k, v in pkg.data["settings"].items() if k not in MACHINE_SETTINGS}
                    self.settings.replace_many(clean)
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES('data_changed_since_backup', 'true') "
                    "ON CONFLICT(key) DO UPDATE SET value = 'true'")
        except BaseException:
            for f in written_files:  # پاک‌سازی پیوست‌های نیمه‌کاره
                f.unlink(missing_ok=True)
            raise
        for f in old_files:
            f.unlink(missing_ok=True)
        return result

    def _has_data(self) -> bool:
        return any(self.db.query_one(f"SELECT 1 FROM {t} LIMIT 1") for t in ("prompts", "categories", "templates"))

    # --- دسته‌بندی‌ها ---
    def _import_categories(self, conn, pkg: Package, result: ImportResult) -> dict[str, int]:
        incoming = pkg.data.get("categories", [])
        by_uuid = {c["uuid"]: c for c in incoming}
        existing_uuid = {r["uuid"]: r["id"] for r in conn.execute("SELECT id, uuid FROM categories").fetchall()}
        mapping: dict[str, int] = dict(existing_uuid)
        pending = [c for c in incoming if c["uuid"] not in mapping]
        guard = 0
        while pending and guard < 50:
            guard += 1
            rest = []
            for c in pending:
                parent_uuid = c.get("parent_uuid")
                if parent_uuid and parent_uuid in by_uuid and parent_uuid not in mapping:
                    rest.append(c)
                    continue
                parent_id = mapping.get(parent_uuid) if parent_uuid else None
                # اگر هم‌نام و هم‌والد وجود دارد، همان استفاده شود تا دسته‌ی تکراری ساخته نشود
                same = conn.execute(
                    "SELECT id FROM categories WHERE name = ? AND parent_id IS ?", (c["name"], parent_id)).fetchone()
                if same:
                    mapping[c["uuid"]] = same["id"]
                    continue
                cur = conn.execute(
                    "INSERT INTO categories(uuid, name, parent_id, icon, color, sort_order, created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (c["uuid"], c["name"], parent_id, c.get("icon", "📁"), c.get("color", "#6C63FF"),
                     int(c.get("sort_order", 0) or 0), c.get("created_at") or now_iso()))
                mapping[c["uuid"]] = cur.lastrowid
                result.categories_added += 1
            pending = rest
        return mapping

    # --- قالب‌ها ---
    def _import_templates(self, conn, pkg, cat_map, mode, default_action, decisions, result) -> None:
        for t in pkg.data.get("templates", []):
            action = decisions.get(t["uuid"], default_action)
            cat_id = cat_map.get(t.get("category_uuid"))
            ex = conn.execute("SELECT * FROM templates WHERE uuid = ?", (t["uuid"],)).fetchone()
            if ex is None:
                ex = conn.execute("SELECT * FROM templates WHERE title = ?", (t["title"].strip(),)).fetchone()
                is_conflict = ex is not None
            else:
                same = ex["title"] == t["title"] and ex["body"] == t.get("body", "")
                if same:
                    continue
                is_conflict = True
            if ex is not None and is_conflict:
                if action == SKIP:
                    continue
                if action == REPLACE:
                    conn.execute(
                        "UPDATE templates SET title=?, body=?, description=?, category_id=?, updated_at=? WHERE id=?",
                        (t["title"], t.get("body", ""), t.get("description", ""), cat_id, now_iso(), ex["id"]))
                    result.templates_replaced += 1
                    continue
                new_uuid = str(uuidlib.uuid4())
                title = f"{t['title']} (وارد‌شده)"
            else:
                new_uuid, title = t["uuid"], t["title"]
            conn.execute(
                "INSERT INTO templates(uuid, title, body, description, category_id, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (new_uuid, title, t.get("body", ""), t.get("description", ""), cat_id,
                 t.get("created_at") or now_iso(), t.get("updated_at") or now_iso()))
            result.templates_added += 1

    # --- پرامپت‌ها ---
    def _import_prompts(self, conn, pkg, cat_map, mode, default_action, decisions, result, written_files) -> None:
        for p in pkg.data.get("prompts", []):
            body = p.get("body", "")
            ex = conn.execute("SELECT * FROM prompts WHERE uuid = ?", (p["uuid"],)).fetchone()
            conflict = False
            if ex is not None:
                if _same_content({"title": ex["title"], "body": ex["body"]}, p):
                    result.skipped += 1
                    continue
                conflict = True
            else:
                ex = conn.execute("SELECT * FROM prompts WHERE title = ?", (p["title"].strip(),)).fetchone()
                if ex is None and body.strip():
                    nb = normalize(body)
                    for r in conn.execute("SELECT * FROM prompts WHERE length(body) = length(?)", (body,)).fetchall():
                        if normalize(r["body"]) == nb:
                            ex = r
                            break
                conflict = ex is not None
            if conflict:
                action = decisions.get(p["uuid"], default_action)
                if action == SKIP:
                    result.skipped += 1
                    continue
                if action == REPLACE:
                    self._replace_prompt(conn, ex, p, cat_map, pkg, result, written_files)
                    result.replaced += 1
                    continue
                self._insert_prompt(conn, p, cat_map, pkg, result, written_files, new_uuid=str(uuidlib.uuid4()),
                                    title_suffix=" (وارد‌شده)")
                result.duplicated += 1
                continue
            self._insert_prompt(conn, p, cat_map, pkg, result, written_files)
            result.added += 1

    def _set_tags(self, conn, prompt_id: int, tags: list[str]) -> None:
        conn.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt_id,))
        seen = set()
        for t in tags:
            t = str(t).strip().lstrip("#").strip()
            if not t or normalize(t) in seen:
                continue
            seen.add(normalize(t))
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (t,))
            tid = conn.execute("SELECT id FROM tags WHERE name = ?", (t,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO prompt_tags(prompt_id, tag_id) VALUES(?,?)", (prompt_id, tid))

    def _insert_prompt(self, conn, p, cat_map, pkg, result, written_files, new_uuid=None, title_suffix="") -> int:
        uid = new_uuid or p["uuid"]
        if conn.execute("SELECT 1 FROM prompts WHERE uuid = ?", (uid,)).fetchone():
            uid = str(uuidlib.uuid4())
        ts = p.get("created_at") or now_iso()
        cur = conn.execute(
            "INSERT INTO prompts(uuid, title, body, category_id, platform, output_type, notes, status, importance, "
            "favorite, pinned, archived, deleted_at, use_count, last_used_at, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, p["title"] + title_suffix, p.get("body", ""), cat_map.get(p.get("category_uuid")),
             p.get("platform", ""), p.get("output_type", ""), p.get("notes", ""), p.get("status", "فعال"),
             int(p.get("importance", 2) or 2), int(bool(p.get("favorite"))), int(bool(p.get("pinned"))),
             int(bool(p.get("archived"))), p.get("deleted_at"), int(p.get("use_count", 0) or 0),
             p.get("last_used_at"), ts, p.get("updated_at") or ts))
        pid = cur.lastrowid
        self._set_tags(conn, pid, p.get("tags", []))
        versions = p.get("versions") or [{
            "version_no": 1, "title": p["title"], "body": p.get("body", ""), "note": "نسخه‌ی اولیه", "created_at": ts}]
        for i, v in enumerate(sorted(versions, key=lambda x: x.get("version_no", 0)), start=1):
            conn.execute(
                "INSERT INTO versions(prompt_id, version_no, title, body, note, created_at) VALUES(?,?,?,?,?,?)",
                (pid, i, v.get("title", p["title"]), v.get("body", ""), v.get("note", ""), v.get("created_at") or ts))
        self._import_attachments(conn, pid, p, pkg, result, written_files)
        self.prompts._reindex(conn, pid)
        return pid

    def _replace_prompt(self, conn, ex, p, cat_map, pkg, result, written_files) -> None:
        """جایگزینی: متن قبلی در تاریخچه‌ی نسخه‌ها می‌ماند، پس چیزی برای همیشه از بین نمی‌رود."""
        pid = ex["id"]
        conn.execute(
            "UPDATE prompts SET title=?, body=?, category_id=?, platform=?, output_type=?, notes=?, status=?, "
            "importance=?, favorite=?, pinned=?, archived=?, updated_at=? WHERE id=?",
            (p["title"], p.get("body", ""), cat_map.get(p.get("category_uuid")), p.get("platform", ""),
             p.get("output_type", ""), p.get("notes", ""), p.get("status", "فعال"),
             int(p.get("importance", 2) or 2), int(bool(p.get("favorite"))), int(bool(p.get("pinned"))),
             int(bool(p.get("archived"))), now_iso(), pid))
        self._set_tags(conn, pid, p.get("tags", []))
        have = {(r["title"], r["body"]) for r in conn.execute(
            "SELECT title, body FROM versions WHERE prompt_id = ?", (pid,)).fetchall()}
        nxt = conn.execute("SELECT COALESCE(MAX(version_no),0) FROM versions WHERE prompt_id = ?", (pid,)).fetchone()[0]
        for v in sorted(p.get("versions") or [], key=lambda x: x.get("version_no", 0)):
            key = (v.get("title", p["title"]), v.get("body", ""))
            if key not in have:
                nxt += 1
                have.add(key)
                conn.execute(
                    "INSERT INTO versions(prompt_id, version_no, title, body, note, created_at) VALUES(?,?,?,?,?,?)",
                    (pid, nxt, key[0], key[1], v.get("note", ""), v.get("created_at") or now_iso()))
        if (p["title"], p.get("body", "")) not in have:
            nxt += 1
            conn.execute(
                "INSERT INTO versions(prompt_id, version_no, title, body, note, created_at) VALUES(?,?,?,?,?,?)",
                (pid, nxt, p["title"], p.get("body", ""), "جایگزین‌شده هنگام بازیابی بکاپ", now_iso()))
        self._import_attachments(conn, pid, p, pkg, result, written_files, skip_existing=True)
        self.prompts._reindex(conn, pid)

    def _import_attachments(self, conn, pid, p, pkg, result, written_files, skip_existing: bool = False) -> None:
        existing_hashes = {r["sha256"] for r in conn.execute(
            "SELECT sha256 FROM attachments WHERE prompt_id = ?", (pid,)).fetchall()} if skip_existing else set()
        for a in p.get("attachments", []) or []:
            data = pkg.read_attachment(a.get("stored_name", "")) if pkg.kind == "pvault" else None
            if data is None:
                result.attachments_missing += 1
                continue
            h = hashlib.sha256(data).hexdigest()
            if h in existing_hashes:
                continue
            name = Path(str(a.get("filename", "file"))).name or "file"
            ext = Path(name).suffix.lower()
            from ..services.file_service import ALLOWED_EXTENSIONS, IMAGE_EXTENSIONS
            if ext not in ALLOWED_EXTENSIONS:
                result.attachments_missing += 1
                continue
            kind = a.get("kind") if a.get("kind") in ("file", "image", "result") else "file"
            if kind == "image" and ext not in IMAGE_EXTENSIONS:
                kind = "file"
            stored = f"{uuidlib.uuid4().hex}{ext}"
            dest = self.files.dir / stored
            dest.write_bytes(data)
            written_files.append(dest)
            conn.execute(
                "INSERT INTO attachments(prompt_id, filename, stored_name, size, sha256, created_at, kind) "
                "VALUES(?,?,?,?,?,?,?)",
                (pid, name, stored, len(data), h, a.get("created_at") or now_iso(), kind))
            result.attachments_added += 1
