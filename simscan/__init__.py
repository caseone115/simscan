"""SimScan - offline auditor for The Sims 4 Mods folder.

`__version__` is the single source of truth for the product version. Every other
surface derives from it: the installer filename, the NSIS VIProductVersion, the
Inno Setup AppVersion, the CI filenames, the README install line, the landing
page and the sample report. Nothing else may state a version of its own -
`scripts/check_version_consistency.py` fails the build if anything does.

Versions are plain `x.y.z`. Windows PE version resources need four integers, so
the fourth is appended by `scripts/version.py --four`; it is not written out by
hand anywhere.

1.0.2 (2026-09-30) exists because the v1.0.1 release shipped an installer named
`SimScan-1.0.0-Setup.exe` whose own version resource said `1.0.0` and whose
uninstall entry wrote `DisplayVersion 1.0.0`. Rather than quietly rename that
release's assets, the drift was fixed at the source and a new release cut that a
real Windows runner proves end to end.
"""

__version__ = "1.0.2"
__app_name__ = "SimScan"
APP_TITLE = f"{__app_name__} {__version__}"
