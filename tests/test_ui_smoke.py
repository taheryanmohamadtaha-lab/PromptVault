"""تست دودی رابط کاربری (بدون نمایش واقعی پنجره: QT_QPA_PLATFORM=offscreen).

همه‌ی صفحه‌ها، همه‌ی تم‌ها و جریان‌های اصلی را اجرا می‌کند تا هر دکمه‌ی خراب قبل از ساخت EXE پیدا شود.
اگر PySide6 نصب نباشد، این فایل به‌صورت خودکار رد می‌شود.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import import_manager as im  # noqa: E402
from app.themes.themes import THEME_NAMES  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyle("Fusion")
    return app


@pytest.fixture()
def window(qapp, ctx):
    w = MainWindow(ctx, qapp)
    w.show()
    qapp.processEvents()
    yield w
    w.hotkey.unregister()
    w.quick.close()
    w.hide()
    qapp.processEvents()


def _seed(ctx):
    cats = ctx.categories.flat()
    a = ctx.prompts.create("ساخت اندیکاتور MT5", "یک اندیکاتور بنویس\nخط دوم", cats[7].id, ["MT5", "اندیکاتور"],
                           platform="Claude", importance=3)
    b = ctx.prompts.create("Midjourney portrait", "photo of a cat, 8k", cats[0].id, ["image"], platform="Midjourney")
    c = ctx.prompts.create("بدون دسته", "فقط متن")
    return a, b, c


def test_every_page_opens(window, qapp, ctx):
    _seed(ctx)
    for key in window.pages:
        window.show_page(key)
        qapp.processEvents()
        assert window.stack.currentWidget() is window.pages[key]
        assert window.nav_buttons[key].isChecked()


def test_all_themes_and_font_size(window, qapp, ctx):
    for theme in THEME_NAMES:
        ctx.settings.set("theme", theme)
        ctx.settings.set("accent_color", "#FF7A1A")
        ctx.settings.set("font_size", 13)
        window.apply_theme()
        qapp.processEvents()
        assert "#FF7A1A" in qapp.styleSheet()
    ctx.settings.set("accent_color", "")
    window.apply_theme()


def test_settings_page_changes_theme_live(window, qapp, ctx):
    page = window.pages["settings"]
    window.show_page("settings")
    idx = page.theme.findData("green")
    page.theme.setCurrentIndex(idx)
    qapp.processEvents()
    assert ctx.settings.get("theme") == "green"
    page.font_size.setValue(14)
    assert ctx.settings.get("font_size") == 14
    page.ed_wrap.setChecked(False)
    assert ctx.settings.get("editor_wrap") is False
    page._restore_defaults()


def test_dashboard_counts_and_navigation(window, qapp, ctx):
    _seed(ctx)
    dash = window.pages["dashboard"]
    window.show_page("dashboard")
    assert dash.cards["total"]._value.text() == "3"
    assert dash.sec_added.list.count() == 3
    dash.search.setText("اندیکاتور")
    dash._do_search()
    qapp.processEvents()
    assert window.current == "all"
    assert window.pages["all"].list.count() == 1


def test_list_search_filters_and_actions(window, qapp, ctx):
    a, b, c = _seed(ctx)
    page = window.pages["all"]
    window.show_page("all")
    assert page.list.count() == 3
    page.set_query("اندیکاتور")
    assert page.list.count() == 1
    page.set_query("MIDJOURNEY")               # بدون حساسیت به بزرگی/کوچکی حروف
    assert page.list.count() == 1
    page.reset_filters()
    assert page.list.count() == 3

    page.set_tag("MT5")
    assert page.list.count() == 1
    page.reset_filters()

    page.list.setCurrentRow(0)
    page.list.item(0).setSelected(True)
    pid = page.selected_ids()[0]
    page._copy_current()
    assert QGuiApplication.clipboard().text() == ctx.prompts.get(pid).body
    assert ctx.prompts.get(pid).use_count == 1

    page._toggle_flag("favorite")
    assert ctx.prompts.get(pid).favorite is True
    window.show_page("favorites")
    assert window.pages["favorites"].list.count() == 1
    window.show_page("recent")
    assert window.pages["recent"].list.count() == 1

    window.show_page("all")
    page.list.clearSelection()
    page.list.item(0).setSelected(True)
    before = page.list.count()
    page._duplicate_selected()
    assert page.list.count() == before + 1

    page.list.clearSelection()
    page.list.item(0).setSelected(True)
    page._delete_selected()                     # انتقال به سطل (بدون پرسش)
    assert page.list.count() == before
    window.show_page("trash")
    trash = window.pages["trash"]
    assert trash.list.count() == 1
    trash.list.item(0).setSelected(True)
    trash._restore_selected()
    assert trash.list.count() == 0


def test_archive_and_move(window, qapp, ctx, monkeypatch):
    a, _b, _c = _seed(ctx)
    page = window.pages["all"]
    window.show_page("all")
    page.list.item(0).setSelected(True)
    pid = page.selected_ids()[0]
    page._toggle_flag("archived")
    assert ctx.prompts.get(pid).archived
    window.show_page("archived")
    assert window.pages["archived"].list.count() == 1

    from app.ui import prompt_list

    class FakeMove:
        def __init__(self, *a, **k): ...
        def exec(self): return 1
        def category_id(self): return ctx.categories.flat()[3].id

    monkeypatch.setattr(prompt_list, "MoveDialog", FakeMove)
    window.show_page("all")
    page.list.item(0).setSelected(True)
    moved = page.selected_ids()[0]
    page._move_selected()
    assert ctx.prompts.get(moved).category_id == ctx.categories.flat()[3].id


def test_editor_creates_and_edits_prompt(window, qapp, ctx):
    from app.ui.prompt_editor import PromptEditorDialog
    dlg = PromptEditorDialog(ctx, None, window)
    dlg.title.setText("پرامپت از ویرایشگر")
    dlg.body.setPlainText("متن کامل ۱")
    assert dlg.save_now()
    pid = dlg.prompt_id
    assert pid and ctx.prompts.get(pid).title == "پرامپت از ویرایشگر"
    dlg.body.setPlainText("متن کامل ۲")
    assert dlg.save_now()
    assert ctx.prompts.get(pid).body == "متن کامل ۲"
    dlg.copy_prompt()
    assert QGuiApplication.clipboard().text() == "متن کامل ۲"
    dlg.reject()
    reopened = PromptEditorDialog(ctx, pid, window)
    assert reopened.body.toPlainText() == "متن کامل ۲"
    reopened.reject()


def test_categories_and_tags_page(window, qapp, ctx, monkeypatch):
    _seed(ctx)
    from app.ui import categories as cat_ui
    page = window.pages["categories"]
    window.show_page("categories")
    assert page.tree.topLevelItemCount() == len(ctx.categories.tree())

    class FakeDialog:
        def __init__(self, *a, **k): ...
        def exec(self): return 1
        def values(self): return ("دسته‌ی تست", "🧪", "#112233")

    monkeypatch.setattr(cat_ui, "CategoryDialog", FakeDialog)
    n = page.tree.topLevelItemCount()
    page._add(None)
    assert page.tree.topLevelItemCount() == n + 1
    new = [c for c in ctx.categories.flat() if c.name == "دسته‌ی تست"][0]
    page._add(new.id)                           # زیردسته
    assert any(c.parent_id == new.id for c in ctx.categories.flat())

    assert page.tag_list.count() >= 1           # برچسب‌های seed
    page.tag_list.setCurrentRow(0)
    page._cur_tag()


def test_templates_page_flow(window, qapp, ctx):
    page = window.pages["templates"]
    window.show_page("templates")
    n = page.list.count()
    assert n >= 1                               # قالب‌های اولیه
    page._new()
    assert page.list.count() == n + 1
    page.title.setText("قالب تست")
    page.body.setPlainText("برنامه {{APP_NAME}} برای {{PLATFORM}}")
    assert "APP_NAME" in page.vars_label.text()
    assert page._save()
    assert any(t.title == "قالب تست" for t in ctx.templates.list())
    page._duplicate()
    assert page.list.count() == n + 2


def test_backup_page_and_restore_preview(window, qapp, ctx, tmp_path, monkeypatch):
    _seed(ctx)
    from app.ui import backup_window
    monkeypatch.setattr(backup_window, "info", lambda *a, **k: None)
    page = window.pages["backup"]
    window.show_page("backup")
    page._backup(str(tmp_path / "bk"))
    files = list((tmp_path / "bk").glob("*.pvault"))
    assert len(files) == 1
    pkg = im.load_package(files[0])
    dlg = backup_window.ImportPreviewDialog(ctx, pkg, window)
    opts = dlg.options()
    assert opts["mode"] == "merge"
    dlg.reject()
    page.auto.enabled.setChecked(True)
    page.auto.keep.setValue(3)
    assert ctx.settings.get("backup_auto_enabled") is True and ctx.settings.get("backup_keep") == 3


def test_quick_search_copies(window, qapp, ctx):
    a, _b, _c = _seed(ctx)
    q = window.quick
    q.popup()
    q.input.setText("اندیکاتور")
    q._search()
    assert q.list.count() == 1
    q._copy_current()
    assert QGuiApplication.clipboard().text() == ctx.prompts.get(a.id).body


def test_startup_page_setting(qapp, ctx):
    ctx.settings.set("startup_page", "favorites")
    w = MainWindow(ctx, qapp)
    assert w.current == "favorites"
    w.hotkey.unregister()
    w.quick.close()
    w.close()


def test_editor_fits_small_screen_and_has_visible_save(window, qapp, ctx):
    """دکمه‌ی ذخیره نباید بیرون از مانیتور بیفتد: پنجره از ناحیه‌ی قابل‌استفاده‌ی صفحه بزرگ‌تر نیست."""
    from app.ui.prompt_editor import PromptEditorDialog
    dlg = PromptEditorDialog(ctx, None, window)
    dlg.show()
    qapp.processEvents()
    avail = (dlg.screen() or QGuiApplication.primaryScreen()).availableGeometry()
    assert dlg.width() <= avail.width() and dlg.height() <= avail.height()
    assert dlg.minimumHeight() <= avail.height() and dlg.minimumWidth() <= avail.width()
    assert dlg.save_btn.isVisible() and dlg.top_save_btn.isVisible()
    # دکمه‌ی بالایی ذخیره می‌کند و پنجره را باز نگه می‌دارد
    dlg.title.setText("ذخیره‌ی بالایی")
    dlg.top_save_btn.click()
    assert dlg.prompt_id and ctx.prompts.get(dlg.prompt_id).title == "ذخیره‌ی بالایی" and dlg.isVisible()
    dlg.reject()


def test_editor_result_panel_image_and_code(window, qapp, ctx, monkeypatch):
    from PySide6.QtGui import QImage

    from app.ui.prompt_editor import PromptEditorDialog
    dlg = PromptEditorDialog(ctx, None, window)
    dlg.title.setText("با تصویر و کد")
    assert dlg.save_now()
    pid = dlg.prompt_id
    panel = dlg.result_panel
    # تصویر از کلیپ‌بورد
    img = QImage(40, 30, QImage.Format_RGB32)
    img.fill(0xFF3366)
    QGuiApplication.clipboard().setImage(img)
    panel.paste_image()
    imgs = ctx.files.list(pid, "image")
    assert len(imgs) == 1 and panel.img_list.count() == 1 and panel._img_pix is not None
    # کد از کلیپ‌بورد (بدون پنجره‌ی پرسش نام فایل)
    code = ctx.files.add_text(pid, "final.mq5", "int OnInit(){return 0;}", kind="result")
    panel.refresh(select_result=code.id)
    assert panel.res_list.count() == 1 and "OnInit" in panel.res_view.toPlainText()
    panel.copy_code()
    assert "OnInit" in QGuiApplication.clipboard().text()
    # پیش‌نمایش در فهرست
    window.show_page("prompts")
    page = window.pages["prompts"]
    page.refresh()
    qapp.processEvents()
    page._show_result_preview(pid)
    assert not page.p_img.isHidden() and not page.p_result.isHidden()
    # حذف
    panel.img_list.setCurrentRow(0)
    from app.ui import result_panel as rp
    monkeypatch.setattr(rp, "confirm", lambda *a, **k: True)
    panel.remove_image()
    assert ctx.files.list(pid, "image") == []
    dlg.reject()

