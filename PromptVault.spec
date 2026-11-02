# -*- mode: python ; coding: utf-8 -*-
# ساخت نسخه‌ی مستقل ویندوز:  pyinstaller --noconfirm --clean PromptVault.spec
# خروجی: dist/PromptVault/PromptVault.exe  (پوشه‌ای؛ سریع‌تر اجرا می‌شود و کمتر با آنتی‌ویروس مشکل دارد)
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "app" / "assets"), "app/assets")],
    hiddenimports=[],
    excludes=[
        "tkinter", "unittest", "pytest",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
        "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.QtQml",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort",
        "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtPositioning", "PySide6.QtLocation",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PromptVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "app" / "assets" / "icon.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PromptVault",
)
