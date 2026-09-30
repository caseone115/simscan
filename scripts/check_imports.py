#!/usr/bin/env python3
"""Import every module the packaged build depends on, and fail loudly if any
does not. Run before PyInstaller in CI so a broken import stops the build
instead of shipping an exe that cannot start.

    python scripts/check_imports.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODULES = [
    "simscan",
    "simscan.analyzer",
    "simscan.dbpf",
    "simscan.dds",
    "simscan.discovery",
    "simscan.report",
    "simscan.recyclex",
    "simscan.cli",
    "simscan.__main__",
    "simscan.gui",
]

failed = []
for name in MODULES:
    try:
        importlib.import_module(name)
    except Exception as ex:            # noqa: BLE001 - report anything at all
        failed.append(f"{name}: {type(ex).__name__}: {ex}")

if failed:
    for f in failed:
        print("  FAIL:", f)
    raise SystemExit(f"{len(failed)} module(s) failed to import")

from simscan import __version__        # noqa: E402

print(f"imports OK ({len(MODULES)} modules), version {__version__}")
