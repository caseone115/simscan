"""Export scan results as reports (HTML, CSV, JSON, text)."""
import csv
import html
import io
import json
import os
import time

from . import __version__

SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
SEV_LABEL = {"high": "High", "medium": "Medium", "low": "Low", "info": "Info"}


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


def to_json(result, path):
    data = {
        "tool": f"SimScan {__version__}",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mods_folder": result.root,
        "stats": result.stats,
        "warnings": result.warnings,
        "findings": [
            {
                "kind": f.kind,
                "severity": f.severity,
                "title": f.title,
                "detail": f.detail,
                "fix": f.fix,
                "evidence": f.evidence,
                "files": [m.rel_path for m in f.files],
            }
            for f in result.findings
        ],
        "files": [
            {
                "path": m.rel_path,
                "size": m.size,
                "kind": m.kind,
                "sha256": m.content_hash,
                "resources": m.resources,
                "display_name": m.display_name,
                "creator": m.creator,
                "priority": m.priority,
                "load_order": m.order_index,
                "error": m.error,
            }
            for m in result.files
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path


def to_csv(result, path):
    cols = ["path", "name", "kind", "size_bytes", "resources", "display_name",
            "creator", "priority", "load_order", "sha256", "error"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for m in result.files:
            w.writerow([m.rel_path, m.name, m.kind, m.size, m.resources,
                        m.display_name or "", m.creator or "", m.priority,
                        m.order_index, m.content_hash or "", m.error or ""])
    return path


def to_text(result, path):
    L = []
    L.append(f"SimScan {__version__} - Mods folder report")
    L.append(f"Folder : {result.root}")
    L.append(f"Scanned: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    s = result.stats
    L.append(f"Files  : {s.get('total_files',0)} "
             f"({s.get('packages',0)} packages, {s.get('scripts',0)} scripts, "
             f"{human_bytes(s.get('total_bytes',0))})")
    L.append("")
    for f in sorted(result.findings, key=lambda x: SEV_ORDER[x.severity]):
        L.append(f"[{SEV_LABEL[f.severity]}] {f.title}")
        L.append(f"    {f.detail}")
        if f.fix:
            L.append(f"    Fix: {f.fix}")
        for m in f.files[:40]:
            L.append(f"      - {m.rel_path}")
        if len(f.files) > 40:
            L.append(f"      ... and {len(f.files)-40} more")
        L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return path


def to_html(result, path):
    e = html.escape
    s = result.stats
    parts = []
    parts.append(f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>SimScan report - {e(result.root)}</title>
<style>
 body{{font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
   margin:0;background:#0f1420;color:#e8ecf4}}
 .wrap{{max-width:960px;margin:0 auto;padding:32px 20px 64px}}
 h1{{font-size:26px;margin:0 0 4px}}
 .sub{{color:#8b98ad;margin-bottom:24px;font-size:13px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px}}
 .card{{background:#171e2e;border:1px solid #232c40;border-radius:10px;
   padding:14px 18px;min-width:120px}}
 .card b{{display:block;font-size:22px}}
 .card span{{color:#8b98ad;font-size:12px;text-transform:uppercase;
   letter-spacing:.04em}}
 .finding{{background:#171e2e;border:1px solid #232c40;border-left-width:4px;
   border-radius:10px;padding:16px 18px;margin-bottom:14px}}
 .high{{border-left-color:#ef4444}} .medium{{border-left-color:#f59e0b}}
 .low{{border-left-color:#3b82f6}} .info{{border-left-color:#64748b}}
 .finding h3{{margin:0 0 6px;font-size:16px}}
 .pill{{font-size:11px;padding:2px 8px;border-radius:99px;
   background:#232c40;color:#a9b6cc;margin-right:8px;text-transform:uppercase}}
 .detail{{color:#c2ccdd;margin:6px 0}}
 .fix{{color:#7fd1a6;font-size:13px;margin-top:8px}}
 .files{{margin:10px 0 0;padding-left:18px;color:#93a1b8;font-size:13px}}
 .files li{{margin:2px 0;word-break:break-all}}
 .more{{color:#8b98ad;font-size:12px;margin-top:6px}}
 table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}}
 th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #232c40}}
 th{{color:#8b98ad;font-weight:500}}
 footer{{color:#5d6a80;font-size:12px;margin-top:40px}}
</style></head><body><div class="wrap">
<h1>SimScan report</h1>
<div class="sub">{e(result.root)} &middot; {time.strftime('%Y-%m-%d %H:%M:%S')}
 &middot; SimScan {__version__}</div>
<div class="cards">
 <div class="card"><b>{s.get('total_files',0)}</b><span>Files</span></div>
 <div class="card"><b>{s.get('packages',0)}</b><span>Packages</span></div>
 <div class="card"><b>{s.get('scripts',0)}</b><span>Script mods</span></div>
 <div class="card"><b>{human_bytes(s.get('total_bytes',0))}</b><span>Size</span></div>
 <div class="card"><b>{s.get('high',0)}</b><span>High issues</span></div>
</div>""")

    if not result.findings:
        parts.append("<p>No problems found. Your Mods folder is clean.</p>")

    for f in sorted(result.findings, key=lambda x: SEV_ORDER[x.severity]):
        parts.append(f'<div class="finding {f.severity}">')
        parts.append(f'<h3><span class="pill">{SEV_LABEL[f.severity]}</span>'
                     f'{e(f.title)}</h3>')
        parts.append(f'<div class="detail">{e(f.detail)}</div>')
        if f.evidence:
            parts.append(f'<div class="detail"><em>Evidence: '
                         f'{e(f.evidence)}</em></div>')
        if f.fix:
            parts.append(f'<div class="fix">&#10003; {e(f.fix)}</div>')
        if f.files:
            parts.append('<ul class="files">')
            for m in f.files[:60]:
                parts.append(f"<li>{e(m.rel_path)}</li>")
            parts.append("</ul>")
            if len(f.files) > 60:
                parts.append(f'<div class="more">...and {len(f.files)-60} '
                             f'more</div>')
        parts.append("</div>")

    parts.append("</div></body></html>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return path


def to_50_50_plan(result, path, suspect_paths, batch=100):
    """Generate a bucketify/unbucketify plan for manual 50-50 testing."""
    L = []
    L.append("SimScan - 50/50 (binary search) test plan")
    L.append("=" * 60)
    L.append("")
    L.append("The game refuses to run, so it cannot tell us which mod is")
    L.append("guilty. This plan narrows it down in a handful of launches")
    L.append("instead of hundreds.")
    L.append("")
    L.append(f"Suspects: {len(suspect_paths)} files")
    L.append(f"Buckets : {(len(suspect_paths)+batch-1)//max(1,batch)} "
             f"folders of {batch}")
    L.append("")
    L.append("HOW TO RUN IT")
    L.append("-" * 60)
    L.append("1. Back up your Mods folder first. Always.")
    L.append("2. Create a folder named  _disabled  inside Mods.")
    L.append("3. Move HALF the suspect files listed below into _disabled.")
    L.append("   (A folder starting with an underscore is how SimScan, and")
    L.append("    most organisers, mark content the game should skip.)")
    L.append("4. Launch the game.")
    L.append("   - It works  -> the culprit was in the half you removed;")
    L.append("                  put that half back and remove the other half.")
    L.append("   - It fails  -> the culprit is still installed; keep the")
    L.append("                  half you left in place and halve again.")
    L.append("5. Repeat. Each launch halves the suspects.")
    L.append("")
    L.append("Expected launches to find the culprit: "
             f"~{(len(suspect_paths) or 1).bit_length()}")
    L.append("")
    L.append("SUSPECT FILES (grouped into suggested buckets)")
    L.append("-" * 60)
    for i in range(0, len(suspect_paths), batch):
        chunk = suspect_paths[i:i + batch]
        L.append("")
        L.append(f"--- Bucket {i//batch + 1} "
                 f"({len(chunk)} files) ---")
        for p in chunk:
            L.append(f"    {p}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return path
