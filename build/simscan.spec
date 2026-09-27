# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SimScan (Windows).

Build:  pyinstaller --clean --noconfirm build/simscan.spec
Output: dist/SimScan/SimScan.exe  (plus a portable single-file build)
"""
import os

block_cipher = None

# PyInstaller exec()s this spec, so __file__ is undefined. It does inject
# SPECPATH for us, so prefer that and fall back to the working directory.
try:
    SPEC_DIR = SPECPATH                      # noqa: F821 (injected)
except NameError:                            # pragma: no cover
    SPEC_DIR = os.getcwd()
ROOT = os.path.abspath(os.path.join(SPEC_DIR, ".."))
ICON = os.path.join(ROOT, "assets", "simscan.ico")

a = Analysis(
    [os.path.join(SPEC_DIR, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        "simscan", "simscan.gui", "simscan.cli", "simscan.analyzer",
        "simscan.dbpf", "simscan.dds", "simscan.report", "simscan.recyclex",
        "simscan.discovery",
        "PIL", "PIL.Image", "PIL.ImageTk", "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy", "scipy", "matplotlib", "pandas", "pytest",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython", "notebook",
        "setuptools", "pip", "wheel",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SimScan",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,              # GUI app: never show a console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON if os.path.exists(ICON) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SimScan",
)
