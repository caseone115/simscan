#!/usr/bin/env bash
# SimScan Windows release build. All logic lives in scripts/build_installer.py
# so that this file contains no version and no destructive shell command.
#   ./build/build_windows.sh
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/build_installer.py "$@"
