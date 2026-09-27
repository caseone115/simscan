"""SimScan command line interface.

Same engine as the GUI. Useful on its own, and it is how the build is
smoke-tested headlessly.
"""
import argparse
import os
import sys
import time

from . import APP_TITLE
from .analyzer import scan_mods_folder, find_exception_files, correlate_exception
from .discovery import find_mods_dir, user_folder_for
from . import report as report_mod

SEV_LABEL = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW", "info": "INFO"}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="simscan", description=f"{APP_TITLE} - offline audit of a Sims 4 "
                                    "Mods folder.")
    ap.add_argument("folder", nargs="?", default=None,
                    help="Mods folder (auto-detected if omitted)")
    ap.add_argument("--json", metavar="FILE", help="write JSON report")
    ap.add_argument("--csv", metavar="FILE", help="write CSV report")
    ap.add_argument("--html", metavar="FILE", help="write HTML report")
    ap.add_argument("--txt", metavar="FILE", help="write text report")
    ap.add_argument("--quiet", action="store_true", help="summary only")
    ap.add_argument("--no-hash", action="store_true",
                    help="skip content hashing (much faster, no duplicates)")
    ap.add_argument("--exception", metavar="N", type=int, default=None,
                    help="analyse the Nth newest LastException file")
    args = ap.parse_args(argv)

    root = args.folder or find_mods_dir()
    if not root or not os.path.isdir(root):
        print("Could not find a Sims 4 Mods folder. Pass one explicitly:\n"
              "  simscan \"C:\\Users\\you\\Documents\\Electronic Arts\\"
              "The Sims 4\\Mods\"")
        return 2

    last = [""]

    def prog(msg):
        if not args.quiet:
            print(f"\r  {msg:<60}", end="", flush=True)
        last[0] = msg

    print(f"{APP_TITLE}")
    print(f"Scanning: {root}")
    t0 = time.time()
    res = scan_mods_folder(root, progress=prog,
                           hash_files=not args.no_hash)
    if not args.quiet:
        print("\r" + " " * 66 + "\r", end="")

    s = res.stats
    print(f"\n{s.get('total_files',0)} files  |  "
          f"{s.get('packages',0)} packages  |  "
          f"{s.get('scripts',0)} script "
          f"{'mod' if s.get('scripts',0)==1 else 'mods'}  |  "
          f"{report_mod.human_bytes(s.get('total_bytes',0))}  |  "
          f"{res.duration:.1f}s")

    if res.warnings:
        for w in res.warnings:
            print(f"  warning: {w}")

    if not res.findings:
        print("\nNo problems found.")
    for f in sorted(res.findings, key=lambda x: SEV_ORDER[x.severity]):
        print(f"\n[{SEV_LABEL[f.severity]}] {f.title}")
        if not args.quiet:
            print(f"    {f.detail}")
            if f.fix:
                print(f"    Fix: {f.fix}")
            for m in f.files[:15]:
                print(f"      - {m.rel_path}")
            if len(f.files) > 15:
                print(f"      ... and {len(f.files)-15} more "
                      f"(use --txt for the full list)")

    if args.exception is not None:
        uf = user_folder_for(root)
        files = find_exception_files(uf)
        if not files:
            print("\nNo LastException files found.")
        else:
            idx = max(0, min(args.exception, len(files) - 1))
            p = files[idx]
            print(f"\nCrash report: {os.path.basename(p)}")
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            info, ranked = correlate_exception(text, res.files)
            print(f"  exception: {info.get('exception') or 'n/a'}")
            print(f"  {len(ranked)} suspect(s):")
            for path, score, why in ranked[:20]:
                m = next((x for x in res.files if x.abs_path == path), None)
                rel = m.rel_path if m else os.path.basename(path)
                print(f"    {score:5.1f}  {rel}   [{'; '.join(why)}]")

    written = []
    if args.json:
        written.append(report_mod.to_json(res, args.json))
    if args.csv:
        written.append(report_mod.to_csv(res, args.csv))
    if args.html:
        written.append(report_mod.to_html(res, args.html))
    if args.txt:
        written.append(report_mod.to_text(res, args.txt))
    for w in written:
        print(f"\nWrote {w}")

    return 1 if s.get("high") else 0


if __name__ == "__main__":
    sys.exit(main())
