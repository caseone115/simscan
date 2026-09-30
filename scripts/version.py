#!/usr/bin/env python3
"""The one place the product version is decided.

    python scripts/version.py          # 1.0.2
    python scripts/version.py --four   # 1.0.2.0  (a PE VERSIONINFO needs 4 parts)
    python scripts/version.py --check  # assert the source is parseable and sane

Every other surface derives from `simscan/__init__.py:__version__` - the installer
filename, the Inno Setup AppVersion, the NSIS VIProductVersion, the CI filenames,
the README install line, the landing page and the sample report.

Reads the value by PARSING THE SOURCE FILE, not by importing the package, and
that is deliberate. On 2026-09-30 this script returned `1.0.0` while
`simscan/__init__.py` said `1.0.2`: the two versions are the same number of
bytes, so Python's bytecode-cache check (mtime + size) accepted a stale
`__pycache__/__init__.cpython-*.pyc` and imported the old number. A version
accessor that can be fooled by a stale cache would have silently approved a
release built at the wrong version. Parsing the text cannot be.

`--check` also asserts the parsed value agrees with the imported one, so a
genuine divergence between the two readings is reported rather than hidden.

Added 2026-09-30 because the release was tagged v1.0.1 while shipping
`SimScan-1.0.0-Setup.exe`, whose internal version was `1.0.0` and whose uninstall
entry wrote `DisplayVersion 1.0.0`. A winget manifest asserts a version and then
checks the *installed* version, so that mismatch was the first thing a moderator
would have rejected.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "simscan" / "__init__.py"
PATTERN = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.M)
PLAIN = re.compile(r"^\d+\.\d+\.\d+$")


def source_version() -> str:
    """The version as written in the source. No import, no bytecode cache."""
    m = PATTERN.search(SOURCE.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"{SOURCE} has no top-level __version__ = \"x.y.z\"")
    return m.group(1)


def imported_version() -> str:
    """The version Python actually loads. Must equal `source_version()`."""
    out = subprocess.run(
        [sys.executable, "-c", "import simscan; print(simscan.__version__)"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return out.stdout.strip()


def four_part(v: str) -> str:
    """`1.0.2` -> `1.0.2.0`. Windows version resources require four integers."""
    parts = [p for p in v.split(".") if p != ""]
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts[:4])


def main(argv: list[str]) -> int:
    v = source_version()

    if "--check" in argv:
        problems = []
        if not PLAIN.match(v):
            problems.append(f"__version__ {v!r} is not a plain x.y.z version")
        four = four_part(v)
        if len(four.split(".")) != 4 or not all(p.isdigit() for p in four.split(".")):
            problems.append(f"four-part form {four!r} is malformed")
        got = imported_version()
        if got != v:
            problems.append(
                f"the source says {v} but importing simscan gives {got!r} - a stale "
                f"__pycache__ would explain it; delete simscan/__pycache__ and retry"
            )
        for p in problems:
            print("  FAIL:", p)
        if problems:
            raise SystemExit(1)
        print(f"version {v} (four-part {four}), source and import agree")
        return 0

    print(four_part(v) if "--four" in argv else v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
