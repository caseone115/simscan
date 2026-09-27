"""Frozen-app entry point.

PyInstaller executes its entry script as a top-level module, so a file using
relative imports (like ``simscan/__main__.py``) fails with "attempted
relative import with no known parent package". This launcher uses absolute
imports and is the entry point the .spec file points at.
"""
import sys


def main():
    from simscan.__main__ import main as app_main
    return app_main()


if __name__ == "__main__":
    sys.exit(main())
