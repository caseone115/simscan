#!/usr/bin/env bash
# Build the Windows release of SimScan on Linux.
#
#   ./build/build_windows.sh
#
# Produces:
#   dist/SimScan/                       portable app folder
#   dist/installer/SimScan-1.0.0-Setup.exe   one-click installer
#
# Requirements: wine (64-bit), makensis, python3-venv, pillow, pyinstaller.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="1.0.0"
WINEPREFIX="${WINEPREFIX:-$HOME/.wine-simscan}"
export WINEPREFIX
export WINEDEBUG=-all

say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

say "Checking tools"
command -v wine     >/dev/null || { echo "wine not installed";     exit 1; }
command -v makensis >/dev/null || { echo "makensis not installed"; exit 1; }
command -v python3  >/dev/null || { echo "python3 not installed";  exit 1; }
wine --version

say "Preparing build virtualenv (Linux side)"
if [ ! -d ".venv-build" ]; then
  python3 -m venv .venv-build
fi
# shellcheck disable=SC1091
source .venv-build/bin/activate
pip install --quiet --upgrade pip
pip install --quiet pillow pyinstaller

say "Running the test suite before building"
python -m pytest -q tests 2>/dev/null || python tests/run_tests.py

say "Booting Wine prefix (initialises .wine-simscan)"
wineboot -u >/dev/null 2>&1 || true
sleep 2

say "Installing Windows Python into the Wine prefix"
PYVER="3.11.9"
PYEXE="python-${PYVER}-amd64.exe"
PYURL="https://www.python.org/ftp/python/${PYVER}/${PYEXE}"
CACHE="build/cache"
mkdir -p "$CACHE"
if [ ! -f "$CACHE/$PYEXE" ]; then
  echo "  downloading $PYEXE"
  curl -fL --retry 3 -o "$CACHE/$PYEXE" "$PYURL"
fi
if ! wine "$WINEPREFIX/drive_c/Python311/python.exe" -V >/dev/null 2>&1; then
  echo "  installing (silent)…"
  wine "$CACHE/$PYEXE" /quiet InstallAllUsers=0 PrependPath=0 \
       Include_test=0 Include_launcher=0 TargetDir='C:\Python311' \
       >/dev/null 2>&1
  sleep 5
fi
WINPY="$WINEPREFIX/drive_c/Python311/python.exe"
wine "$WINPY" -V

say "Installing build dependencies inside Wine"
wine "$WINPY" -m pip install --quiet --upgrade pip
wine "$WINPY" -m pip install --quiet pillow pyinstaller

say "Building the Windows executable"
rm -rf dist/SimScan build/pyi build/__pycache__ 2>/dev/null || true
wine "$WINPY" -m PyInstaller --clean --noconfirm \
     --distpath "dist" --workpath "build/pyi" \
     build/simscan.spec

if [ ! -f "dist/SimScan/SimScan.exe" ]; then
  echo "FAILED: dist/SimScan/SimScan.exe was not produced"
  exit 1
fi
say "Executable built: $(du -sh dist/SimScan | cut -f1)"

say "Smoke-testing the packaged app (CLI mode, via Wine)"
SAMPLES="$ROOT/build/samples"
if [ -d "$SAMPLES" ]; then
  WINPATH="$(winepath -w "$SAMPLES" 2>/dev/null || echo '')"
  if [ -n "$WINPATH" ]; then
    wine "dist/SimScan/SimScan.exe" --cli "$WINPATH" --quiet || true
  fi
fi

say "Building the installer (native makensis, no 32-bit Wine needed)"
mkdir -p dist/installer
makensis -V2 -DSRCDIR="$(pwd)/dist/SimScan" \
                -DOUTDIR="$(pwd)/dist/installer" \
                build/installer.nsi

say "Done"
ls -la dist/installer/
