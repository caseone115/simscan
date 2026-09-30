#!/usr/bin/env python3
"""Build the Windows release of SimScan.

    python scripts/build_installer.py            # build everything it can
    python scripts/build_installer.py --check    # do not build, only assert

Two build paths, because the host cannot run both:

  * `--windows` on Linux - Wine + PyInstaller produces `dist/SimScan/SimScan.exe`,
    then native `makensis` wraps it into `dist/installer/SimScan-<v>-Setup.exe`.
    This is the path `build/build_windows.sh` runs.
  * CI (`.github/workflows/build-windows.yml`) does the same on a real Windows
    runner with Inno Setup, and additionally installs, runs and uninstalls the
    built installer and asserts the version the OS recorded matches the release.

The version is READ from `scripts/version.py` (single source:
`simscan/__init__.py:__version__`) and passed down to every tool. Nothing in
this file or in `build/installer.nsi` states a version of its own - on
2026-09-30 that is exactly how a v1.0.1 release came to ship an installer called
`SimScan-1.0.0-Setup.exe`, with `1.0.0` inside it and `DisplayVersion 1.0.0` in
its uninstall entry.

After the installer is built, this script reads the built file's *real* Windows
VERSIONINFO resource back and refuses to declare success unless FileVersion,
ProductVersion, the uninstall version and the filename all agree with the
version it was told to build - see `scripts/check_version_consistency.py`.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simscan import __version__ as V  # noqa: E402

DIST = ROOT / "dist"
INSTALLER_DIR = DIST / "installer"
INSTALLER = INSTALLER_DIR / f"SimScan-{V}-Setup.exe"
PORTABLE_APP = DIST / "SimScan"
PORTABLE_ZIP = DIST / f"SimScan-{V}-portable.zip"


def say(msg: str) -> None:
    print(f"\n==> {msg}")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("   $", " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def have(exe: str) -> bool:
    return shutil.which(exe) is not None


def consistency_check(artifact: Path | None = None) -> None:
    cmd = [sys.executable, str(ROOT / "scripts" / "check_version_consistency.py")]
    if artifact is not None:
        cmd.append(str(artifact))
    run(cmd)


# ---------------------------------------------------------------- NSIS (Linux)
def build_nsis() -> Path | None:
    """Wrap an existing `dist/SimScan/` into an installer with native makensis."""
    if not have("makensis"):
        print("   makensis not installed - skipping the NSIS installer")
        return None
    if not PORTABLE_APP.exists():
        print(f"   {PORTABLE_APP} does not exist - nothing to wrap; skipping")
        return None
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    run(["makensis", "-V2",
         f"-DAPPVERSION={V}",
         f"-DVERFOUR={V}.0" if len(V.split(".")) < 4 else f"-DVERFOUR={V}",
         f"-DSRCDIR={PORTABLE_APP}",
         f"-DOUTDIR={INSTALLER_DIR}",
         ROOT / "build" / "installer.nsi"])
    if not INSTALLER.exists():
        print(f"   FAILED: {INSTALLER} was not produced")
        return None
    return INSTALLER


def build_portable_zip() -> Path | None:
    if not PORTABLE_APP.exists():
        return None
    say("Packaging the portable zip")
    import zipfile
    with zipfile.ZipFile(PORTABLE_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PORTABLE_APP.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(PORTABLE_APP))
    print("   wrote", PORTABLE_ZIP.name, f"({PORTABLE_ZIP.stat().st_size} bytes)")
    return PORTABLE_ZIP


def write_sums(files: list[Path]) -> Path:
    say("Writing SHA256SUMS.txt from the files just built")
    import hashlib
    lines = []
    for f in files:
        if f and f.exists():
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            lines.append(f"{h}  {f.name}")
    out = DIST / "SHA256SUMS.txt"
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text().strip() or "   (no files to sum)")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="only assert the version surfaces agree; build nothing")
    args = ap.parse_args(argv)

    say(f"SimScan {V} - release build")
    say("Asserting every surface agrees on the version")
    consistency_check()

    if args.check:
        print("\n--check: nothing was built.")
        return 0

    say("NSIS installer (native makensis)")
    installer = build_nsis()

    portable = build_portable_zip()

    if installer or portable:
        write_sums([f for f in (installer, portable) if f])

    if installer:
        # The last word: read the built installer's own Windows version
        # resource back and make it agree with the release, or fail.
        say("Asserting the built installer carries the version it was given")
        consistency_check(installer)
        print(f"\nBUILT: {installer}")
    else:
        print("\nNo installer was produced on this host. On Linux the Windows "
              "executable needs `build/build_windows.sh` (Wine + PyInstaller); "
              "CI builds and acceptance-tests it on a real Windows runner.")
    if portable:
        print(f"BUILT: {portable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
