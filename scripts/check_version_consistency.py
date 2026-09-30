#!/usr/bin/env python3
"""Every surface must agree on one version. Fails loudly if any does not.

    python scripts/check_version_consistency.py
    python scripts/check_version_consistency.py --artifact dist/installer/SimScan-1.0.1-Setup.exe

Why this exists (2026-09-30): the release was tagged `v1.0.1` but shipped
`SimScan-1.0.0-Setup.exe`, whose own Windows version resource said `1.0.0` and
whose uninstall entry wrote `DisplayVersion 1.0.0`. Three surfaces, three
different answers to "what version is this?", and nothing in the repository
noticed. A winget manifest asserts a version and then verifies the version the
installer actually installed, so that drift was the first thing a moderator would
have rejected.

Two layers, because they catch different faults:

  * STATIC - a surface that is *supposed to be told* the version must not carry a
    hard-coded one. This is what stops the drift coming back. The patterns are
    exact per file, not a blanket "any x.y.z number": an earlier draft of this
    check flagged its own docstring examples and an unrelated Python version,
    which is precisely the false-alarm failure the project has already paid for
    once on the shop probe.
  * ARTIFACT (`--artifact`) - reads a *built* installer's real Windows
    VERSIONINFO resource and asserts FileVersion/ProductVersion/filename all
    agree. Catches a build that ignored the version it was handed, which no
    source check can.

Exit 0 = consistent. Exit 1 = inconsistent, with the offending surface named.
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Read the version by PARSING the source, never by importing it. On 2026-09-30
# importing returned 1.0.0 while the source said 1.0.2 - the two are the same
# number of bytes, so Python's bytecode cache accepted a stale .pyc. A guard
# that can be fooled by a cache would have approved a release built at the
# wrong version; parsing cannot be.
from version import imported_version, source_version  # noqa: E402

V = source_version()
_IMPORTED = imported_version()
_STALE_CACHE_CLEARED = False

if _IMPORTED != V:
    # A mismatch here is very often not a real disagreement but a stale
    # __pycache__ entry. `1.0.2` and `9.9.9` are the same byte length, so
    # CPython's cache check (mtime + size) accepts the old bytecode: observed on
    # 2026-09-30, when this file's own fault-injection test left the guard
    # insisting the version was 9.9.9 while the source plainly said 1.0.2.
    # Purge the caches for the package, re-import once, and only then judge.
    cleared = []
    for d in sorted((ROOT / "simscan").rglob("__pycache__")):
        for f in d.glob("*.pyc"):
            f.unlink()
            cleared.append(f.name)
        try:
            d.rmdir()
        except OSError:
            pass
    for f in (ROOT / "scripts" / "__pycache__").glob("version*.pyc"):
        f.unlink()
        cleared.append(f.name)
    if cleared:
        _STALE_CACHE_CLEARED = True
        _IMPORTED = imported_version()

FAILS: list[str] = []
NOTES: list[str] = []


def fail(msg: str) -> None:
    FAILS.append(msg)


def read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        fail(f"{rel}: missing")
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


_VER = r"\d+\.\d+\.\d+(?:\.\d+)?"

# Per-surface: a list of (regex, explanation). Each is a pattern that means
# "this file decided a version for itself". Prose and comments are not matched
# because the patterns are structural, not "any version-looking number".
# Each surface declares its OWN comment markers. This matters: Inno Setup uses
# `;` for comments and `#` for preprocessor directives, so treating `#` as a
# comment made the .iss pattern unmatchable - the guard simply could not see a
# hard-coded `#define AppVersion`, which is precisely the drift that shipped in
# v1.0.1. An earlier draft skipped every `#` line for all four surfaces and
# missed that fault on a fault-injection test.
DERIVED: list[tuple[str, str, tuple[str, ...], list[tuple[str, str]]]] = [
    ("build/installer.nsi",
     "NSIS: the version must arrive via -DAPPVERSION / -DVERFOUR",
     (";", "#"),
     [(r'^\s*!define\s+APPVERSION\s+"', "defines its own APPVERSION"),
      (r'^\s*VIProductVersion\s+"\d',
       "hard-codes VIProductVersion instead of ${VERFOUR}"),
      (rf'^\s*OutFile\s+.*{_VER}', "hard-codes the version in the output filename"),
      (rf'^\s*WriteRegStr.*DisplayVersion.*{_VER}',
       "hard-codes DisplayVersion in the uninstall entry")]),
    ("build/simscan.iss",
     "Inno Setup: the version must arrive via /DAppVersion",
     (";",),
     [(r'^\s*#define\s+AppVersion\s+"', "defines its own AppVersion"),
      (rf'^\s*VersionInfo(Version|ProductVersion)\s*=\s*\d',
       "hard-codes VersionInfoVersion instead of {#VerFour}")]),
    ("build/build_windows.sh",
     "the build script must read scripts/version.py",
     ("#",),
     [(r'^\s*VERSION=', "sets its own VERSION"),
      (rf'--?DAPPVERSION=\s*{_VER}',
       "passes a literal APPVERSION instead of reading it")]),
    (".github/workflows/build-windows.yml",
     "CI must compute filenames from the version it read, never from a literal",
     ("#",),
     [(rf'SimScan-{_VER}', "hard-codes a versioned filename")]),
]

for rel, why, comments, pats in DERIVED:
    txt = read(rel)
    if not txt:
        continue
    for i, line in enumerate(txt.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(comments):
            continue
        for pat, expl in pats:
            if re.search(pat, line):
                fail(f"{rel}:{i} {expl} ({why}) :: {stripped[:90]}")

# The workflow must derive, not guess.
WF = read(".github/workflows/build-windows.yml")
if WF and "scripts/version.py" not in WF:
    fail(".github/workflows/build-windows.yml never reads scripts/version.py")

# pyproject must not keep a second copy of the number.
PP = read("pyproject.toml")
if PP:
    m = re.search(r'^version\s*=\s*"([^"]+)"', PP, re.M)
    if m:
        fail(f"pyproject.toml hard-codes version = {m.group(1)!r}; it must be "
             f"dynamic from simscan.__version__ (single source)")
    if 'dynamic = ["version"]' not in PP:
        fail("pyproject.toml does not declare version as dynamic")
    if 'attr = "simscan.__version__"' not in PP:
        fail("pyproject.toml does not point its dynamic version at simscan.__version__")

# scripts/version.py is the accessor: it must read the source, not restate it.
VA = read("scripts/version.py")
if VA:
    if 'source_version' not in VA:
        fail("scripts/version.py does not parse __version__ out of the source")
    # A *top-level* import of the package would trust the bytecode cache.
    # An `import simscan` inside a subprocess (the --check cross-read) is fine,
    # and an earlier draft of this rule flagged it - the same false-alarm
    # mistake the shop probe made, so the pattern is anchored to line start.
    if re.search(r"^(from simscan import|import simscan)", VA, re.M):
        fail("scripts/version.py imports the package at module level for the "
             "version - a stale __pycache__ would let it read the wrong number")

# The value the source states and the value Python loads must be the same.
if _IMPORTED != V:
    fail(f"the source says {V} but importing simscan gives {_IMPORTED!r} even after "
         f"clearing the bytecode cache - the version really does disagree")
if _STALE_CACHE_CLEARED:
    NOTES.append("a stale __pycache__ entry was found and cleared (same-length "
                 "version bump defeats CPython's mtime+size cache check)")

# ------------------------------------------------- surfaces that NAME it
README = read("README.md")
if README:
    m = re.search(r"Download `(SimScan-[^`]+-Setup\.exe)`", README)
    if not m:
        fail("README.md: no `Download SimScan-<version>-Setup.exe` line found")
    elif m.group(1) != f"SimScan-{V}-Setup.exe":
        fail(f"README.md names {m.group(1)}, but the version is {V} "
             f"(should be SimScan-{V}-Setup.exe)")

PAGE = read("docs/index.html")
if PAGE:
    named = set(re.findall(r"SimScan\s+(\d+\.\d+\.\d+)", PAGE))
    if not named:
        fail("docs/index.html names no SimScan version")
    for n in sorted(named - {V}):
        fail(f"docs/index.html names version {n}, but the product is {V}")

NOTES.append(f"source version: {V}")

# ------------------------------------------------- the built artifact
def artifact_version(path: Path) -> dict:
    """Read the real Windows VERSIONINFO resource out of a built exe."""
    data = path.read_bytes()
    marker = ("V\x00S\x00_\x00V\x00E\x00R\x00S\x00I\x00O\x00N\x00_\x00I\x00N\x00F\x00O\x00"
              ).encode("latin-1")
    i = data.find(marker)
    if i < 0:
        return {"has_version_resource": False}
    base = i - 6

    def u16(o): return struct.unpack_from("<H", data, o)[0]

    def wstr(o):
        e = o
        while data[e:e + 2] != b"\x00\x00":
            e += 2
        return data[o:e].decode("utf-16-le", "replace"), e + 2

    def a4(o): return o + ((4 - ((o - base) % 4)) % 4)

    info: dict[str, str] = {}

    def node(o, end, depth=0):
        while o + 6 <= end:
            wl, wvl, wt = u16(o), u16(o + 2), u16(o + 4)
            if wl == 0:
                return
            key, after = wstr(o + 6)
            p = a4(after)
            val = None
            if wt == 1:
                val, _ = wstr(p)
                nxt = a4(p + wvl * 2)
            else:
                nxt = a4(p + wvl) if wvl else p
            if val is not None:
                info.setdefault(key, val)
            if wt != 1 and depth < 3:
                node(p, min(o + wl, end), depth + 1)
            if nxt <= o:
                return
            o = nxt

    node(base, base + struct.unpack_from("<H", data, base)[0])
    _, after = wstr(base + 6)
    ffi = a4(after)
    _, _, fms, fls, pms, pls = struct.unpack_from("<IIIIII", data, ffi)
    fmt = lambda ms, ls: "%d.%d.%d.%d" % (ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff)
    return {
        "has_version_resource": True,
        "fixed_FileVersion": fmt(fms, fls),
        "fixed_ProductVersion": fmt(pms, pls),
        "strings": {k: v.strip() for k, v in info.items()},
    }


WANT4 = V if len(V.split(".")) == 4 else V + ".0"
for a in [x for x in sys.argv[1:] if not x.startswith("-")]:
    p = Path(a)
    if not p.exists():
        fail(f"artifact {a}: not found")
        continue
    got = artifact_version(p)
    if not got.get("has_version_resource"):
        fail(f"{p.name}: no VERSIONINFO resource at all")
        continue
    s = got["strings"]
    if got["fixed_FileVersion"] != WANT4:
        fail(f"{p.name}: fixed FileVersion {got['fixed_FileVersion']} != {WANT4}")
    if s.get("FileVersion") != WANT4:
        fail(f"{p.name}: FileVersion string {s.get('FileVersion')!r} != {WANT4!r}")
    if s.get("ProductVersion") != V:
        fail(f"{p.name}: ProductVersion string {s.get('ProductVersion')!r} != {V!r}")
    m = re.search(r"SimScan-(\d+\.\d+\.\d+)-Setup\.exe$", p.name)
    if not m:
        fail(f"{p.name}: installer filename carries no version")
    elif m.group(1) != V:
        fail(f"{p.name}: filename says {m.group(1)}, version is {V}")
    NOTES.append(f"{p.name}: FileVersion={got['fixed_FileVersion']} "
                 f"ProductVersion={s.get('ProductVersion')!r}")

print("version consistency check")
for n in NOTES:
    print("  -", n)
if FAILS:
    print()
    for f in FAILS:
        print("  FAIL:", f)
    print(f"\nINCONSISTENT: {len(FAILS)} problem(s).")
    raise SystemExit(1)
print("\nOK: one version everywhere - source, pyproject, installer scripts, build script, "
      "CI workflow, README, landing page"
      + (", and the built artifact's own Windows version resource" if len(sys.argv) > 1 else "") + ".")
