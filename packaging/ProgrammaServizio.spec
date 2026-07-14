# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — shared by macOS and Windows.

Build (from the project root, on the TARGET platform — PyInstaller cannot
cross-compile):
    macOS:   bash packaging/build_mac.sh
    Windows: packaging\\build_windows.bat   (doppio clic)

What gets bundled: the app code, its Python dependencies, assets/ (icons +
font) and bibles/*.db ONLY. No personal data ships: config/ (settings,
scalette salvate, cronologia), hymn folders, lesson files, templates and
music are all configured by each user and live in their own per-user data
folder (see core/paths.py).
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all

APP_NAME = "Gestione programma SDARM"
# SPECPATH (set by PyInstaller) is the packaging/ dir — the project root is
# its parent.
ROOT = os.path.dirname(SPECPATH)

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
]
# Seed bibles: every *.db in bibles/ (the only bundled content, per design).
for f in sorted(os.listdir(os.path.join(ROOT, "bibles"))):
    if f.lower().endswith(".db"):
        datas.append((os.path.join(ROOT, "bibles", f), "bibles"))

binaries = []
hiddenimports = [
    "tools.convert_bib",   # imported lazily by Impostazioni → Bibbia
    "access_parser",       # optional .bib import backend (soft dependency)
]

# Packages whose data files / dynamic libs PyInstaller's static analysis
# misses: customtkinter (theme JSONs), tkinterdnd2 (tkdnd binaries),
# imageio_ffmpeg (the bundled ffmpeg executable), ffpyplayer (ffmpeg libs).
for pkg in ("customtkinter", "tkinterdnd2", "imageio_ffmpeg", "ffpyplayer"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy.f2py", "scipy", "pandas", "IPython",
              "pytest", "setuptools", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    icon_file = os.path.join(ROOT, "assets", "app_icon.icns")
elif sys.platform == "win32":
    icon_file = os.path.join(ROOT, "assets", "app_icon.ico")
else:
    icon_file = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # windowed app — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon_file,
        bundle_identifier="org.sdarm.gestioneprogramma",
        version="1.0.0",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": "1.0.0",
            "NSHumanReadableCopyright": "",
        },
    )
