"""نقطه‌ی شروع برنامه‌ی گنجینه پرامپت (PromptVault)."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _log_path() -> Path:
    from app.utils.paths import config_dir
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "error.log"


def run_selftest(app, out_file: str) -> int:
    """بررسی خودکار برای CI: برنامه (حتی نسخه‌ی EXE) با داده‌ی موقت بالا می‌آید، همه‌ی صفحه‌ها و تم‌ها را
    باز می‌کند و یک بکاپ سالم می‌سازد. نتیجه در فایل out_file نوشته می‌شود (EXE بدون کنسول است)."""
    import os
    import tempfile

    try:
        tmp = tempfile.mkdtemp(prefix="pv_selftest_")
        os.environ["PROMPTVAULT_DATA_DIR"] = tmp
        from app.core.context import AppContext
        from app.themes.themes import THEME_NAMES
        from app.ui.main_window import MainWindow

        ctx = AppContext(tmp)
        cats = ctx.categories.flat()
        ctx.prompts.create("نمونه‌ی خودآزمون", "متن آزمایشی", cats[0].id, ["test"])
        window = MainWindow(ctx, app)
        window.show()
        for key in window.pages:
            window.show_page(key)
            app.processEvents()
        for theme in THEME_NAMES:
            ctx.settings.set("theme", theme)
            window.apply_theme()
            app.processEvents()
        bk = ctx.backups.create_backup(Path(tmp) / "bk")
        ctx.backups.verify(bk)
        window.hotkey.unregister()
        window.quick.close()
        window.close()
        ctx.close()
        Path(out_file).write_text("SELFTEST OK\n", encoding="utf-8")
        return 0
    except BaseException:  # noqa: BLE001
        Path(out_file).write_text("SELFTEST FAILED\n" + traceback.format_exc(), encoding="utf-8")
        return 1


def main() -> int:
    from PySide6.QtCore import QLockFile, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app import APP_NAME_EN, APP_NAME_FA
    from app.core.context import AppContext
    from app.ui.main_window import MainWindow, app_icon
    from app.ui.style import apply_theme
    from app.utils.paths import get_data_dir

    if sys.platform == "win32":
        try:  # آیکون درست در نوار وظیفه
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PromptVault.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME_EN)
    app.setApplicationDisplayName(APP_NAME_FA)
    app.setOrganizationName(APP_NAME_EN)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        try:
            QMessageBox.critical(None, "خطای برنامه",
                                 f"خطای غیرمنتظره رخ داد. اطلاعات شما در امان است.\n\n{exc}\n\n"
                                 f"گزارش فنی ذخیره شد:\n{_log_path()}")
        except Exception:
            pass

    sys.excepthook = excepthook

    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        return run_selftest(app, sys.argv[i + 1] if i + 1 < len(sys.argv) else "selftest.txt")

    data_dir = get_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        QMessageBox.critical(None, APP_NAME_FA, f"ساخت پوشه‌ی داده ممکن نشد:\n{data_dir}\n\n{e}")
        return 1

    lock = QLockFile(str(data_dir / "promptvault.lock"))
    if not lock.tryLock(300):
        QMessageBox.information(None, APP_NAME_FA, "برنامه از قبل در حال اجراست.")
        return 0

    try:
        ctx = AppContext(data_dir)
    except Exception as e:  # noqa: BLE001
        QMessageBox.critical(
            None, APP_NAME_FA,
            f"باز کردن پایگاه داده ممکن نشد:\n{e}\n\nپوشه‌ی داده‌ها:\n{data_dir}\n"
            "اگر بکاپ دارید، برنامه را با پوشه‌ی داده‌ی تازه اجرا کنید و بکاپ را بازیابی کنید.")
        return 1

    if not ctx.db.integrity_ok():
        QMessageBox.warning(
            None, APP_NAME_FA,
            "بررسی سلامت پایگاه داده مشکلی نشان داد. فوراً از اطلاعات بکاپ بگیرید "
            "(بخش «بکاپ و انتقال») و در صورت نیاز آخرین بکاپ سالم را بازیابی کنید.")

    apply_theme(app, ctx.settings)
    window = MainWindow(ctx, app)
    window.show()
    code = app.exec()
    ctx.close()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
