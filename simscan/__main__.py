"""SimScan entry point."""
import sys


def main():
    # GUI by default; `simscan --cli ...` or `python -m simscan.cli` for the
    # command line. If tkinter is unavailable we fall back to the CLI.
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from .cli import main as cli_main
        return cli_main(sys.argv[2:])
    try:
        import tkinter  # noqa: F401
    except Exception:
        from .cli import main as cli_main
        return cli_main(sys.argv[1:])
    from .gui import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
