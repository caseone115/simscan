#!/usr/bin/env python3
"""Regenerate the published sample report from the engine that ships.

    python scripts/build_sample_report.py

`docs/sample-report.html` is the artifact the landing page invites a buyer to
open - "a real report, not a mock-up". It was generated once, by hand, on
2026-09-29. Nothing regenerated it, so it kept the version it was born with and
would have gone on saying `1.0.0` while the product moved on. That is the same
class of drift this tick fixed in the installer.

This script plants the same deliberate defects the published report describes,
runs the *real* `simscan.analyzer` over them and writes the report with the
*real* `simscan.report.to_html`. No fixture is hand-written and no text is
invented: every filename, count and finding in the output came out of a run.

The landing page's description of the folder is asserted against what the run
actually found, so the page cannot quietly drift from the report either.
"""
from __future__ import annotations

import re
import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simscan import __version__, analyzer, report  # noqa: E402

OUT = ROOT / "docs" / "sample-report.html"

# Names the landing page promises a reader will see in the report.
EXPECTED = [
    "ScriptMods/MCCC/mc_cmd_center.ts4script",
    "Loose Files/JacBaconIsLife (1).package",
    "[MOD] SimmerTales/Jac_BaconIsLife.package",
    "[MOD] TraitPackA/Bold_Trait_v1.package",
    "[MOD] TraitPackB/Bold_Trait_Remake.package",
    "[MOD] TraitPackA/Hair_A.package",
    "[MOD] TraitPackA/Hair_A_copy.package",
    "Loose Files/empty.package",
    "Downloads/mod.zip",
    "Downloads/readme.txt",
    "Loose Files/Broken.url",
]


def write_package(path: Path, resources) -> None:
    """Minimal uncompressed DBPF 2.1 writer - the same writer the test suite
    uses, so the published sample report is produced by the shipped engine
    reading exactly the kind of file the suite validates against."""
    buf = bytearray(b"\x00" * 96)
    index = []
    for (t, g, inst), payload in resources:
        off = len(buf)
        buf.extend(payload)
        index.append((t, g, (inst >> 32) & 0xFFFFFFFF, inst & 0xFFFFFFFF,
                      off, len(payload), len(payload)))
    index_pos = len(buf)
    buf.extend(struct.pack("<I", 0))
    for t, g, iex, ilo, off, raw_len, size in index:
        buf.extend(struct.pack("<IIIIIII", t, g, iex, ilo, off, raw_len, size))
    index_size = len(buf) - index_pos
    buf[0:4] = b"DBPF"
    struct.pack_into("<II", buf, 0x04, 2, 1)
    struct.pack_into("<II", buf, 0x0C, 0, 0)
    struct.pack_into("<I", buf, 0x24, len(index))
    struct.pack_into("<I", buf, 0x28, index_pos)
    struct.pack_into("<I", buf, 0x2C, index_size)
    struct.pack_into("<I", buf, 0x40, 0)
    struct.pack_into("<I", buf, 0x44, 3)
    struct.pack_into("<I", buf, 0x48, index_pos)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))


def build_fixture(root: Path) -> None:
    """The deliberately broken Mods folder the page describes."""
    # two pairs of byte-identical files under different names
    # TWO pairs, each pair identical to its twin and different from the other -
    # which is what the landing page promises a reader will see ("two pairs of
    # identical files under different names").
    pair_a = [((0x545AC67A, 0, 5), b"jac-bacon-payload")]
    pair_b = [((0x034AEECB, 0, 7), b"hair-payload")]
    write_package(root / "Loose Files" / "JacBaconIsLife (1).package", pair_a)
    write_package(root / "[MOD] SimmerTales" / "Jac_BaconIsLife.package", pair_a)
    write_package(root / "[MOD] TraitPackA" / "Hair_A.package", pair_b)
    write_package(root / "[MOD] TraitPackA" / "Hair_A_copy.package", pair_b)
    # a resource conflict between two trait mods, different payloads
    key = (0x545AC67A, 0, 0x2F1A3C4D5E6F7788)
    write_package(root / "[MOD] TraitPackA" / "Bold_Trait_v1.package",
                  [(key, b"bold-v1")])
    write_package(root / "[MOD] TraitPackB" / "Bold_Trait_Remake.package",
                  [(key, b"bold-v2-different")])
    # a script mod buried two levels deep: the game never loads it
    deep = root / "ScriptMods" / "MCCC"
    deep.mkdir(parents=True, exist_ok=True)
    (deep / "mc_cmd_center.ts4script").write_bytes(b"PK\x03\x04 script")
    # A package with a valid header, a valid empty index, and no resources:
    # the "valid header, zero content" finding. Written with the same DBPF
    # writer, given nothing to put in it.
    write_package(root / "Loose Files" / "empty.package", [])
    # junk that should not be in Mods
    (root / "Downloads").mkdir(parents=True, exist_ok=True)
    (root / "Downloads" / "mod.zip").write_bytes(b"PK\x03\x04")
    (root / "Downloads" / "readme.txt").write_text("read me\n")
    (root / "Loose Files" / "Broken.url").write_text("[InternetShortcut]\n")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="simscan-sample-"))
    root = tmp / "Mods"
    build_fixture(root)

    result = analyzer.scan_mods_folder(str(root))
    report.to_html(result, str(OUT))

    html = OUT.read_text(encoding="utf-8")
    # The report prints an absolute temp path and a wall-clock time. The
    # published page is a sample: keep the folder description stable and the
    # timestamp honest-but-not-tied-to-this-host.
    html = html.replace(str(root), "Mods (example folder)")
    html = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                  time.strftime("%Y-%m-%d %H:%M:%S"), html)
    OUT.write_text(html, encoding="utf-8")

    # Assert the page's own description against what the run found. If the
    # engine stops producing one of these, the page must be rewritten, not left
    # claiming it.
    missing = [n for n in EXPECTED if n not in html]
    if missing:
        for m in missing:
            print("  FAIL: the report does not name", m)
        raise SystemExit(f"{len(missing)} file(s) the landing page promises are absent")

    # The landing page describes this folder in prose. Assert the prose against
    # the run, not the other way round.
    SUB = [
        ("a script mod buried too deep", "script mod that will never load"),
        ("two pairs of identical files under different names",
         "2 duplicated mods (2 wasted)"),
        ("a resource conflict between two trait mods",
         "resource conflict between mods"),
        ("an empty package", "package with no content"),
        ("some junk that should not be there",
         "files that should not be in Mods"),
    ]
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    # The page is wrapped at ~80 columns, so match on collapsed whitespace.
    page = " ".join(page.split())
    for prose, title in SUB:
        if prose not in page:
            print(f"  FAIL: the landing page no longer describes {prose!r}")
            raise SystemExit("the landing page and the report have drifted apart")
        if title not in html:
            print(f"  FAIL: the report no longer shows {title!r}")
            raise SystemExit("the landing page promises a finding the report does not make")
    print(f"  asserted {len(SUB)} prose claims on the landing page against the report")

    counts = {}
    for m in re.finditer(r"<b>(\d+)</b><span>([^<]+)</span>", html):
        counts[m.group(2)] = int(m.group(1))
    sev = {s: len(re.findall(rf'class="finding {s}"', html)) for s in
           ("high", "medium", "low", "info")}

    print(f"wrote {OUT.relative_to(ROOT)} with SimScan {__version__}")
    print("  counts:", counts)
    print("  findings by severity:", sev)
    print(f"  asserted {len(EXPECTED)} filenames the landing page promises")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
