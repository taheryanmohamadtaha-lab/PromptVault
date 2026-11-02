import json
import zipfile

import pytest

from app.core import import_manager as im
from app.core.import_manager import PVaultError, load_package
from app.services.search_service import PromptFilter


def _populate(ctx, tmp_path):
    cats = ctx.categories.flat()
    sub = ctx.categories.add("زیر‌دسته من", cats[0].id, "⭐", "#ff0000")
    p1 = ctx.prompts.create("پرامپت یک", "متن یک", sub.id, ["AI", "تست"], platform="Claude", importance=3)
    ctx.prompts.update(p1.id, body="متن یک - ویرایش‌شده", version_note="v2")
    p2 = ctx.prompts.create("Prompt two", "second body", cats[1].id, ["video"])
    ctx.prompts.set_favorite(p2.id, True)
    ctx.prompts.mark_used(p2.id)
    f = tmp_path / "ref.txt"
    f.write_text("پیوست مرجع", encoding="utf-8")
    ctx.files.add(p1.id, f)
    ctx.templates.create("قالب من", "سلام {{NAME}}")
    ctx.settings.set("theme", "purple")
    return p1, p2


def test_full_transfer_to_fresh_install(ctx, ctx2, tmp_path):
    """سناریوی اصلی: بکاپ از کامپیوتر اول، بازیابی روی نصب تازه‌ی کامپیوتر دوم."""
    _populate(ctx, tmp_path)
    backup = ctx.backups.create_backup(tmp_path / "bk")
    assert backup.suffix == ".pvault" and backup.stat().st_size > 0

    pkg = load_package(backup)
    prev = ctx2.importer.preview(pkg)
    assert prev.counts["new"] >= 3 and prev.conflicts == []
    res = ctx2.importer.apply(pkg, import_settings=True)
    assert res.added == 2 and res.attachments_added == 1 and res.attachments_missing == 0

    got = {p.title: p for p in ctx2.search.search(PromptFilter(view="all"))}
    assert set(got) == {"پرامپت یک", "Prompt two"}
    p1 = got["پرامپت یک"]
    assert p1.body == "متن یک - ویرایش‌شده" and p1.tags == ["AI", "تست"] and p1.importance == 3
    assert [v.version_no for v in ctx2.versions.list(p1.id)] == [2, 1]          # تاریخچه منتقل شد
    atts = ctx2.files.list(p1.id)
    assert len(atts) == 1 and ctx2.files.path_of(atts[0]).read_text(encoding="utf-8") == "پیوست مرجع"
    assert got["Prompt two"].favorite and got["Prompt two"].use_count == 1
    assert any(c.name == "زیر‌دسته من" and c.parent_id for c in ctx2.categories.flat())
    assert any(t.title == "قالب من" for t in ctx2.templates.list())
    assert ctx2.settings.get("theme") == "purple"
    assert ctx2.db.integrity_ok()


def test_merge_detects_duplicates_and_respects_decisions(ctx, ctx2, tmp_path):
    _populate(ctx, tmp_path)
    backup = ctx.backups.create_backup(tmp_path / "bk")
    pkg = load_package(backup)
    ctx2.importer.apply(pkg)
    # دوباره همان بکاپ: همه یکسان‌اند و چیزی تکراری ساخته نمی‌شود
    prev = ctx2.importer.preview(pkg)
    assert prev.counts["identical"] == prev.counts["prompts"] + prev.counts["templates"]
    res = ctx2.importer.apply(pkg)
    assert res.added == 0 and res.skipped == 2 and len(ctx2.search.search(PromptFilter(view="all"))) == 2

    # تغییر محلی در کامپیوتر دوم → تعارض
    local = ctx2.search.search(PromptFilter(query="Prompt two"))[0]
    ctx2.prompts.update(local.id, body="نسخه‌ی محلی")
    prev = ctx2.importer.preview(pkg)
    assert [i.title for i in prev.conflicts] == ["Prompt two"]
    uid = prev.conflicts[0].uuid

    ctx2.importer.apply(pkg, decisions={uid: im.SKIP})
    assert ctx2.prompts.get(local.id).body == "نسخه‌ی محلی"

    ctx2.importer.apply(pkg, decisions={uid: im.BOTH})
    titles = sorted(p.title for p in ctx2.search.search(PromptFilter(view="all")))
    assert titles == ["Prompt two", "Prompt two (وارد‌شده)", "پرامپت یک"]

    ctx2.importer.apply(pkg, decisions={uid: im.REPLACE})
    assert ctx2.prompts.get(local.id).body == "second body"
    # متن محلی قبلی در تاریخچه می‌ماند
    assert any(v.body == "نسخه‌ی محلی" for v in ctx2.versions.list(local.id))


def test_similar_by_title_with_different_uuid(ctx, ctx2, tmp_path):
    _populate(ctx, tmp_path)
    ctx2.prompts.create("پرامپت یک", "متن دیگر")
    pkg = load_package(ctx.backups.create_backup(tmp_path / "bk"))
    prev = ctx2.importer.preview(pkg)
    sim = [i for i in prev.items if i.status == im.SIMILAR]
    assert len(sim) == 1 and sim[0].title == "پرامپت یک"
    ctx2.importer.apply(pkg, default_action=im.SKIP)
    assert len([p for p in ctx2.search.search() if p.title.startswith("پرامپت یک")]) == 1


def test_safety_backup_created_before_restore(ctx, ctx2, tmp_path):
    _populate(ctx, tmp_path)
    ctx2.prompts.create("موجود در مقصد", "x")
    pkg = load_package(ctx.backups.create_backup(tmp_path / "bk"))
    res = ctx2.importer.apply(pkg, safety_dir=tmp_path / "safe")
    assert res.safety_backup and (tmp_path / "safe").is_dir()
    safe = load_package(res.safety_backup)
    assert [p["title"] for p in safe.data["prompts"]] == ["موجود در مقصد"]


def test_replace_all_mode(ctx, ctx2, tmp_path):
    _populate(ctx, tmp_path)
    ctx2.prompts.create("باید حذف شود", "x")
    pkg = load_package(ctx.backups.create_backup(tmp_path / "bk"))
    res = ctx2.importer.apply(pkg, mode="replace_all", safety_dir=tmp_path / "safe")
    assert res.safety_backup
    assert sorted(p.title for p in ctx2.search.search(PromptFilter(view="all"))) == ["Prompt two", "پرامپت یک"]


def test_failed_import_changes_nothing(ctx, ctx2, tmp_path, monkeypatch):
    _populate(ctx, tmp_path)
    ctx2.prompts.create("سالم", "x")
    pkg = load_package(ctx.backups.create_backup(tmp_path / "bk"))
    boom = {"n": 0}
    orig = ctx2.importer._insert_prompt

    def flaky(*a, **k):
        boom["n"] += 1
        if boom["n"] == 2:
            raise RuntimeError("شکست شبیه‌سازی‌شده")
        return orig(*a, **k)

    monkeypatch.setattr(ctx2.importer, "_insert_prompt", flaky)
    with pytest.raises(RuntimeError):
        ctx2.importer.apply(pkg, safety_dir=tmp_path / "safe")
    assert [p.title for p in ctx2.search.search(PromptFilter(view="all"))] == ["سالم"]   # تراکنش برگشت خورد
    assert list(ctx2.attachments_dir.glob("*")) == []                                      # پیوست نیمه‌کاره پاک شد


def test_exports(ctx, tmp_path):
    _populate(ctx, tmp_path)
    out = tmp_path / "exp"
    j = ctx.exporter.export_json(out / "all.json")
    doc = json.loads(j.read_text(encoding="utf-8"))
    assert doc["format"] == "PVault" and len(doc["data"]["prompts"]) == 2
    part = json.loads(ctx.exporter.export_json(out / "p.json", ["prompts"]).read_text(encoding="utf-8"))
    assert "templates" not in part["data"] and "settings" not in part["data"]
    c = ctx.exporter.export_csv(out / "p.csv")
    assert "پرامپت یک" in c.read_text(encoding="utf-8-sig")
    assert "## پرامپت یک" in ctx.exporter.export_markdown(out / "p.md").read_text(encoding="utf-8")
    assert "Prompt two" in ctx.exporter.export_txt(out / "p.txt").read_text(encoding="utf-8")
    # JSON هم قابل بازیابی است (بدون پیوست‌ها)
    pkg = load_package(j)
    assert pkg.kind == "json" and len(pkg.data["prompts"]) == 2


def test_json_roundtrip_import(ctx, ctx2, tmp_path):
    _populate(ctx, tmp_path)
    j = ctx.exporter.export_json(tmp_path / "a.json")
    res = ctx2.importer.apply(load_package(j))
    assert res.added == 2 and res.attachments_missing == 1


# ---------------------------- امنیت و خرابی ----------------------------
def _make_zip(path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for n, d in members.items():
            zf.writestr(n, d)
    return path


def test_zip_slip_rejected(tmp_path):
    for evil in ("../evil.txt", "/abs.txt", "attachments/../../x.txt", "a\\b.txt", "C:/x.txt"):
        z = _make_zip(tmp_path / "e.pvault", {"manifest.json": b"{}", "data.json": b"{}", evil: b"x"})
        with pytest.raises(PVaultError):
            load_package(z)


def test_unlisted_files_rejected(tmp_path):
    z = _make_zip(tmp_path / "e.pvault", {"manifest.json": b"{}", "data.json": b"{}", "other/file.txt": b"x"})
    with pytest.raises(PVaultError):
        load_package(z)


def test_corrupt_and_tampered_backups_rejected(ctx, tmp_path):
    _populate(ctx, tmp_path)
    good = ctx.backups.create_backup(tmp_path / "bk")
    # فایل خراب
    bad = tmp_path / "bad.pvault"
    bad.write_bytes(b"this is not a zip")
    with pytest.raises(PVaultError, match="خراب"):
        load_package(bad)
    # دستکاری data.json با حفظ manifest
    with zipfile.ZipFile(good) as zf:
        members = {n: zf.read(n) for n in zf.namelist()}
    data = json.loads(members["data.json"])
    data["prompts"][0]["body"] = "دستکاری شده"
    members["data.json"] = json.dumps(data, ensure_ascii=False).encode()
    t = _make_zip(tmp_path / "tamper.pvault", members)
    with pytest.raises(PVaultError, match="صحت"):
        load_package(t)
    # پیوست دستکاری‌شده
    att = next(n for n in members if n.startswith("attachments/"))
    members2 = {n: zf_bytes for n, zf_bytes in members.items()}
    with zipfile.ZipFile(good) as zf:
        members2 = {n: zf.read(n) for n in zf.namelist()}
    members2[att] = b"changed"
    t2 = _make_zip(tmp_path / "tamper2.pvault", members2)
    with pytest.raises(PVaultError, match="پیوست"):
        load_package(t2)


def test_wrong_format_and_future_version(tmp_path):
    j = tmp_path / "x.json"
    j.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(PVaultError):
        load_package(j)
    j.write_text(json.dumps({"format": "PVault", "format_version": 99, "data": {}}), encoding="utf-8")
    with pytest.raises(PVaultError, match="جدیدتری"):
        load_package(j)
    with pytest.raises(PVaultError, match="پیدا نشد"):
        load_package(tmp_path / "nope.pvault")


def test_malformed_data_rejected(tmp_path):
    j = tmp_path / "x.json"
    j.write_text(json.dumps({"format": "PVault", "format_version": 1,
                             "data": {"prompts": [{"uuid": "u", "title": ""}]}}), encoding="utf-8")
    with pytest.raises(PVaultError):
        load_package(j)


def test_attachment_path_traversal_in_data_is_neutralised(ctx, ctx2, tmp_path):
    p, _ = _populate(ctx, tmp_path)
    good = ctx.backups.create_backup(tmp_path / "bk")
    pkg = load_package(good)
    pkg.data["prompts"][0]["attachments"][0]["filename"] = "../../evil.txt"
    ctx2.importer.apply(pkg)
    stored = list(ctx2.attachments_dir.iterdir())
    assert len(stored) == 1 and stored[0].parent == ctx2.attachments_dir
    assert ctx2.files.list(ctx2.search.search(PromptFilter(query="پرامپت یک"))[0].id)[0].filename == "evil.txt"


# ---------------------------- بکاپ خودکار ----------------------------
def test_backup_rotation_and_listing(ctx, tmp_path):
    ctx.prompts.create("x", "y")
    ctx.settings.set("backup_dir", str(tmp_path / "auto"))
    ctx.settings.set("backup_keep", 3)
    for _ in range(6):
        ctx.backups.create_backup()
    assert len(ctx.backups.list_backups()) == 6
    removed = ctx.backups.rotate()
    assert len(removed) == 3 and len(ctx.backups.list_backups()) == 3


def test_auto_backup_schedule(ctx, tmp_path):
    from datetime import datetime, timedelta
    ctx.prompts.create("x", "y")
    ctx.settings.set("backup_dir", str(tmp_path / "auto"))
    assert not ctx.backups.due()                              # غیرفعال
    ctx.settings.set("backup_auto_enabled", True)
    ctx.settings.set("backup_schedule", "daily")
    assert ctx.backups.due()
    path = ctx.backups.run_if_due()
    assert path and path.exists()
    assert not ctx.backups.due()
    assert ctx.backups.due(datetime.now() + timedelta(days=1, minutes=1))
    ctx.settings.set("backup_schedule", "weekly")
    assert not ctx.backups.due(datetime.now() + timedelta(days=2))
    assert ctx.backups.due(datetime.now() + timedelta(days=8))


def test_backup_on_exit_modes(ctx, tmp_path):
    ctx.settings.set("backup_dir", str(tmp_path / "auto"))
    ctx.settings.set("backup_auto_enabled", True)
    ctx.settings.set("backup_schedule", "on_exit_if_changed")
    ctx.backups.create_backup()                               # پرچم تغییر پاک می‌شود
    assert ctx.backups.run_on_exit() is None                  # تغییری نبوده
    ctx.prompts.create("جدید", "x")
    assert ctx.backups.run_on_exit() is not None
    assert ctx.backups.run_on_exit() is None
    ctx.settings.set("backup_schedule", "on_exit")
    assert ctx.backups.run_on_exit() is not None


def test_snapshot_of_live_database(ctx, tmp_path):
    ctx.prompts.create("x", "y")
    snap = ctx.db.snapshot_to(tmp_path / "snap.db")
    import sqlite3
    assert sqlite3.connect(snap).execute("SELECT COUNT(*) FROM prompts").fetchone()[0] == 1


def test_works_without_network(ctx, monkeypatch):
    """هیچ‌جای هسته به شبکه نیاز ندارد: هر تلاش برای اتصال، خطا می‌دهد و تست باید باز هم موفق شود."""
    import socket

    def no_net(*a, **k):
        raise AssertionError("تلاش برای اتصال به شبکه!")

    monkeypatch.setattr(socket.socket, "connect", no_net)
    monkeypatch.setattr(socket, "getaddrinfo", no_net)
    p = ctx.prompts.create("آفلاین", "x")
    assert ctx.search.search(PromptFilter(query="آفلاین"))[0].id == p.id
    ctx.backups.create_backup(ctx.data_dir / "bk")
