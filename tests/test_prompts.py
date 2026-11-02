import pytest

from app.services.search_service import PromptFilter
from app.services.template_service import extract_variables, render


def test_create_edit_versions(ctx):
    cat = ctx.categories.flat()[0]
    p = ctx.prompts.create("عنوان اول", "متن اول", cat.id, ["AI", "اندروید"], platform="Claude")
    assert p.id and p.tags == ["AI", "اندروید"]
    assert len(ctx.versions.list(p.id)) == 1

    p2 = ctx.prompts.update(p.id, body="متن دوم", version_note="اصلاح")
    versions = ctx.versions.list(p.id)
    assert [v.version_no for v in versions] == [2, 1]
    assert versions[1].body == "متن اول" and versions[0].note == "اصلاح"
    assert p2.body == "متن دوم"

    # ویرایش بدون تغییر متن/عنوان نسخه‌ی جدید نمی‌سازد
    ctx.prompts.update(p.id, notes="یادداشت")
    assert len(ctx.versions.list(p.id)) == 2

    # بازیابی نسخه‌ی قدیمی، نسخه‌ی فعلی را از بین نمی‌برد
    ctx.versions.restore(p.id, 1)
    assert ctx.prompts.get(p.id).body == "متن اول"
    assert len(ctx.versions.list(p.id)) == 3


def test_empty_title_rejected(ctx):
    with pytest.raises(ValueError):
        ctx.prompts.create("   ", "x")


def test_trash_restore_purge(ctx):
    p = ctx.prompts.create("حذفی", "x")
    ctx.prompts.trash([p.id])
    assert ctx.search.search(PromptFilter()) == []
    assert len(ctx.search.search(PromptFilter(view="trash"))) == 1
    ctx.prompts.restore([p.id])
    assert len(ctx.search.search(PromptFilter())) == 1
    ctx.prompts.trash([p.id])
    ctx.prompts.purge([p.id], ctx.files)
    assert ctx.prompts.get(p.id) is None


def test_duplicate_move_flags_and_use(ctx):
    cats = ctx.categories.flat()
    p = ctx.prompts.create("اصلی", "متن", cats[0].id, ["x"])
    d = ctx.prompts.duplicate(p.id)
    assert d.title == "اصلی (کپی)" and d.tags == ["x"] and d.id != p.id
    ctx.prompts.move([d.id], cats[1].id)
    assert ctx.prompts.get(d.id).category_id == cats[1].id
    ctx.prompts.set_favorite(p.id, True)
    ctx.prompts.set_pinned(p.id, True)
    ctx.prompts.mark_used(p.id)
    ctx.prompts.mark_used(p.id)
    got = ctx.prompts.get(p.id)
    assert got.favorite and got.pinned and got.use_count == 2 and got.last_used_at
    s = ctx.prompts.stats()
    assert s["favorites"] == 1 and s["total"] == 2 and s["total_uses"] == 2


def test_search_persian_english_and_filters(ctx):
    cats = ctx.categories.flat()
    a = ctx.prompts.create("ساخت اندیکاتور", "یک اندیکاتور MT5 كامل بنویس ۱۲۳", cats[7].id, ["MT5"], platform="ChatGPT")
    b = ctx.prompts.create("Image prompt", "A cinematic portrait, 8k", cats[0].id, ["Midjourney"], platform="Midjourney")
    ctx.prompts.set_favorite(b.id, True)
    s = lambda **kw: [p.id for p in ctx.search.search(PromptFilter(**kw))]  # noqa: E731
    assert s(query="اندیکاتور") == [a.id]
    assert s(query="کامل 123") == [a.id]          # ی/ک عربی و ارقام فارسی نرمال می‌شوند
    assert s(query="cinematic") == [b.id]
    assert s(query="CINEMATIC portrait") == [b.id]
    assert s(query="هوش") == [b.id]                # از نام دسته‌ی «تصاویر هوش مصنوعی» پیدا می‌شود
    assert s(query="نامرتبط") == []
    assert s(query="MT5 chatgpt") == [a.id]        # جست‌وجو در پلتفرم و برچسب
    assert s(query="اندیکاتورهای MT5") == [a.id]   # جست‌وجو در نام دسته
    assert s(favorite_only=True) == [b.id]
    assert s(platform="midjourney") == [b.id]
    assert s(tag="mt5") == [a.id]
    assert s(used=False).__len__() == 2
    ctx.prompts.mark_used(a.id)
    assert s(used=True) == [a.id] and s(used=False) == [b.id]
    assert s(query="100%") == []                   # کاراکتر wildcard امن است


def test_category_tree_and_delete(ctx):
    root = ctx.categories.add("ریشه")
    child = ctx.categories.add("فرزند", root.id)
    p = ctx.prompts.create("در فرزند", "x", child.id)
    tree = {c.id: c for c in ctx.categories.tree()}
    assert tree[root.id].count == 1 and tree[root.id].children[0].id == child.id
    assert [x.id for x in ctx.search.search(PromptFilter(category_id=root.id))] == [p.id]
    with pytest.raises(ValueError):
        ctx.categories.reparent(root.id, child.id)       # چرخه ممنوع
    with pytest.raises(ValueError):
        ctx.categories.add("فرزند", root.id)             # نام تکراری هم‌سطح
    ctx.categories.rename(child.id, "نام نو")
    assert [x.id for x in ctx.search.search(PromptFilter(query="نام نو"))] == [p.id]  # ایندکس به‌روز شد
    ctx.categories.delete(child.id, "move", root.id)
    assert ctx.prompts.get(p.id).category_id == root.id
    ctx.categories.delete(root.id, "uncategorize")
    assert ctx.prompts.get(p.id).category_id is None


def test_tags(ctx):
    p = ctx.prompts.create("t", "x", None, ["a", "#b", "A"])
    assert p.tags == ["a", "b"]
    tid = {t.name: t.id for t in ctx.tags.all()}["a"]
    ctx.tags.rename(tid, "b")                            # ادغام
    assert ctx.prompts.get(p.id).tags == ["b"]
    ctx.tags.delete({t.name: t.id for t in ctx.tags.all()}["b"])
    assert ctx.prompts.get(p.id).tags == []


def test_templates(ctx):
    body = "نام: {{APP_NAME}} / {{PLATFORM}} / {{APP_NAME}}"
    assert extract_variables(body) == ["APP_NAME", "PLATFORM"]
    assert render(body, {"APP_NAME": "X", "PLATFORM": ""}) == "نام: X / {{PLATFORM}} / X"
    t = ctx.templates.create("قالب", body)
    d = ctx.templates.duplicate(t.id)
    assert d.title == "قالب (کپی)"
    ctx.templates.update(t.id, "قالب۲", "بدنه")
    assert ctx.templates.get(t.id).title == "قالب۲"
    ctx.templates.delete(d.id)
    assert ctx.templates.get(d.id) is None
    assert len(ctx.templates.list()) >= 4                # قالب‌های پیش‌فرض


def test_similar_prompts(ctx):
    a = ctx.prompts.create("ساخت اندیکاتور RSI", "x", None, ["MT5", "اندیکاتور"])
    b = ctx.prompts.create("ساخت اندیکاتور MACD", "y", None, ["MT5", "اندیکاتور"])
    ctx.prompts.create("دستور پخت", "z", None, ["آشپزی"])
    assert [p.id for p in ctx.prompts.similar(a.id)] == [b.id]


def test_attachments(ctx, tmp_path):
    p = ctx.prompts.create("با پیوست", "x")
    f = tmp_path / "note.txt"
    f.write_text("سلام", encoding="utf-8")
    att = ctx.files.add(p.id, f)
    assert ctx.files.exists(att) and att.size > 0
    bad = tmp_path / "evil.exe"
    bad.write_bytes(b"MZ")
    with pytest.raises(ValueError):
        ctx.files.add(p.id, bad)
    ctx.files.delete(att.id)
    assert not ctx.files.path_of(att).exists()


def test_settings_persist(tmp_path):
    from app.core.context import AppContext
    c = AppContext(tmp_path / "d")
    c.settings.set("theme", "dark")
    c.settings.set("accent_color", "#ff0066")
    c.close()
    c = AppContext(tmp_path / "d")
    assert c.settings.get("theme") == "dark" and c.settings.get("accent_color") == "#ff0066"
    assert c.settings.get("font_size") == 11              # پیش‌فرض
    c.close()


def test_crash_safety_data_survives_without_close(tmp_path):
    """بستن ناگهانی: داده‌ی ثبت‌شده با کامیت در دیتابیس می‌ماند."""
    from app.core.context import AppContext
    c = AppContext(tmp_path / "d")
    c.prompts.create("ماندگار", "x")
    # بدون close() یک اتصال تازه باز می‌کنیم
    c2 = AppContext(tmp_path / "d")
    assert any(p.title == "ماندگار" for p in c2.search.search())
    c2.close()
    c.close()


def test_autosave_does_not_flood_history(ctx):
    p = ctx.prompts.create("عنوان", "یک")
    for i in range(5):                                   # ذخیره‌ی خودکار پشت‌سرهم
        ctx.prompts.update(p.id, body=f"یک {i}", record_version=False)
    assert len(ctx.versions.list(p.id)) == 1
    assert ctx.prompts.get(p.id).body == "یک 4"
    assert ctx.prompts.commit_version(p.id, "ذخیره‌ی دستی") is True
    assert ctx.prompts.commit_version(p.id) is False     # تغییری نیست
    vs = ctx.versions.list(p.id)
    assert len(vs) == 2 and vs[0].body == "یک 4" and vs[1].body == "یک"
