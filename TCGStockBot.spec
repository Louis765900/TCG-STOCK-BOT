# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller pour TCG Stock Bot (application graphique).

Build :  pyinstaller --noconfirm TCGStockBot.spec
Sortie : dist/TCGStockBot/  (dossier complet, avec TCGStockBot.exe)

Note : les navigateurs Playwright (Chromium) NE sont PAS embarqués (lourds et
inutiles pour les enseignes par défaut, qui sont en HTTP/JSON). Le paquet reste
fonctionnel en « mode léger ».
"""
import os

# Données embarquées : l'interface QML + l'icône, et les réglages pré-remplis
# (bundled_settings.json) s'ils existent (pour livrer la machine de Tom prête).
datas = [("gui", "gui")]
if os.path.exists("bundled_settings.json"):
    datas.append(("bundled_settings.json", "."))

# Modules que PyInstaller pourrait ne pas détecter tout seul.
hiddenimports = ["aiosqlite", "aiofiles"]

# On allège : modules Qt lourds et inutiles ici.
excludes = [
    "tkinter",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtBluetooth",
]

a = Analysis(
    ["gui_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TCGStockBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # pas de fenêtre console noire
    disable_windowed_traceback=False,
    icon="gui/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TCGStockBot",
)
