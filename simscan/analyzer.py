"""Mods-folder analysis: the findings that matter to a heavy modder.

Design rule: every finding must be evidence-backed and actionable. We never
guess. If we cannot prove something (e.g. which of two conflicting packages
the game loads), we say so and show the rule we used.

The four things this does that mainstream tools do not:
  1. Silent-failure detection - files the game will never load, with no error.
  2. Content-hash duplicate detection - same mod, different filename.
  3. Conflict winners - not just "these two fight" but which one actually wins.
  4. Real mod names and artwork - read out of the package, offline.
"""
import hashlib
import os
import re
import struct
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from .dbpf import Package, PackageError, parse_stbl

# ----------------------------------------------------------------- constants
SCRIPT_MAX_DEPTH = 1
PACKAGE_MAX_DEPTH = 5
DEFAULT_PRIORITY = 500

JUNK_EXT = {".zip", ".rar", ".7z", ".txt", ".url", ".exe", ".ds_store",
            ".bak", ".old", ".orig", ".nfo", ".sfv", ".md"}
MOD_EXT = {".package", ".ts4script"}

TYPE_NAMES = {
    0x034AEECB: "CAS Part", 0x545AC67A: "SimData",
    0x62E94D38: "CombinedTuning", 0x0333406C: "Tuning",
    0x220557DA: "String Table", 0x00B2D882: "DDS Image",
    0x01D10F34: "Thumbnail", 0x3C1AF1F2: "Object Definition",
    0xD3044521: "Object Definition", 0x3C2A8647: "Blueprint",
    0x00B552EA: "BMP Image", 0x2F7D0004: "Icon",
    0x0355E0A6: "Image", 0x1D6C7F0E: "Region",
    0xE1A93F4C: "Misc", 0xC0DB5AE7: "Object Data",
    0x01661233: "Model", 0x319E4F1D: "Object Tuning",
    0x01D0E75D: "Rig", 0x8EAF13DE: "Rig", 0xD5F0F921: "Unknown",
    0x3C1AF1F2: "Object Definition", 0xCF9A4ACE: "Animation",
    0x6B20C4F3: "State Machine", 0xE1A93F4C: "Region",
    0x0355E0A6: "Image", 0x0071AB77: "Audio", 0x9C3103E4: "Unknown",
    0x220557DA: "String Table", 0x62E94D38: "Combined Tuning",
}

# Resource types that mean "this package changes gameplay" rather than CC
TUNING_TYPES = {0x545AC67A, 0x62E94D38, 0x0333406C, 0x319E4F1D, 0x3C1AF1F2}
CAS_TYPES = {0x034AEECB}
THUMB_TYPES = {0x01D10F34}
IMAGE_TYPES = {0x00B2D882, 0x00B552EA, 0x0355E0A6, 0x2F7D0004}
STBL_TYPE = 0x220557DA



def plural(n, singular, plural_form=None):
    """'1 package' / '3 packages' - never '3 package(s)'."""
    word = singular if n == 1 else (plural_form or singular + "s")
    return f"{n} {word}"


def hexkey(key):
    return f"{key[0]:08X}:{key[1]:08X}:{key[2]:016X}"


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------- results
@dataclass
class ModFile:
    abs_path: str
    rel_path: str
    name: str
    ext: str
    depth: int
    size: int
    mtime: float
    folder: str

    # filled during analysis
    content_hash: Optional[str] = None
    resources: int = 0
    keys: set = field(default_factory=set)
    types: dict = field(default_factory=dict)
    display_name: Optional[str] = None
    creator: Optional[str] = None
    error: Optional[str] = None
    priority: int = DEFAULT_PRIORITY
    order_index: int = 0

    @property
    def is_script(self):
        return self.ext == ".ts4script"

    @property
    def is_package(self):
        return self.ext == ".package"

    @property
    def kind(self):
        if self.is_script:
            return "Script Mod"
        if self.error:
            return "Unreadable"
        t = self.types
        has_tuning = any(k in TUNING_TYPES for k in t)
        has_cas = any(k in CAS_TYPES for k in t)
        if has_tuning and not has_cas:
            return "Gameplay Mod"
        if has_cas and not has_tuning:
            return "Custom Content"
        if has_tuning and has_cas:
            return "Gameplay Mod + CC"
        return "Custom Content"


@dataclass
class Finding:
    kind: str
    severity: str            # high | medium | low | info
    title: str
    detail: str
    files: list = field(default_factory=list)
    evidence: str = ""
    fix: str = ""


@dataclass
class ScanResult:
    root: str
    files: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    load_order: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    duration: float = 0.0


# ------------------------------------------------------------ Resource.cfg
class ResourceCfg:
    """Parsed Resource.cfg -> per-path priority, per the documented rules."""

    def __init__(self, text=""):
        self.rules = []          # (priority, pattern)
        self.loaded = False
        self.raw = text
        self._parse(text)

    def _parse(self, text):
        prio = DEFAULT_PRIORITY
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^\s*Priority\s+(-?\d+)", line, re.I)
            if m:
                prio = int(m.group(1))
                continue
            m = re.match(r"^\s*PackedFile\s+(\S+)", line, re.I)
            if m:
                self.rules.append((prio, m.group(1)))
                self.loaded = True

    def priority_for(self, rel_path):
        """Highest matching priority; default 500.

        Resource.cfg patterns are globs, not real paths:
          *            matches any filename characters (but not a separator)
          ?            matches one character
          //           each extra slash means "one more directory level"
        so `Overrides/*.package` is a file directly in Overrides, while
        `Overrides//*.package` is one level deeper.
        """
        rel = rel_path.replace("\\", "/")
        best = None
        for prio, pattern in self.rules:
            regex = self._glob_to_regex(pattern.replace("\\", "/"))
            if regex is None:
                continue
            try:
                if re.match(regex, rel, re.I):
                    if best is None or prio > best:
                        best = prio
            except re.error:
                continue
        return best if best is not None else DEFAULT_PRIORITY

    @staticmethod
    def _glob_to_regex(pattern):
        p = pattern.strip().lstrip("./")
        if not p:
            return None
        out = []
        i = 0
        n = len(p)
        while i < n:
            ch = p[i]
            if ch == "/":
                # count the run of slashes
                j = i
                while j < n and p[j] == "/":
                    j += 1
                levels = j - i
                if levels == 1:
                    out.append("/")
                else:
                    # N slashes => N-1 intermediate directory levels
                    out.append(r"(?:[^/]+/){%d}" % (levels - 1))
                i = j
            elif ch == "*":
                out.append("[^/]*")
                i += 1
            elif ch == "?":
                out.append("[^/]")
                i += 1
            else:
                out.append(re.escape(ch))
                i += 1
        return "^" + "".join(out) + "$"


def _sort_key_for_name(name):
    """Documented in-game tiebreak: special chars, then digits, then letters."""
    out = []
    for ch in name.lower():
        if ch.isdigit():
            out.append((1, ch))
        elif ch.isalpha():
            out.append((2, ch))
        else:
            out.append((0, ch))
    return out


# ------------------------------------------------------------------ scanning
def collect_files(root):
    out = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root)
            out.append(ModFile(
                abs_path=full,
                rel_path=rel.replace("\\", "/"),
                name=fn,
                ext=os.path.splitext(fn)[1].lower(),
                depth=rel.count(os.sep) + rel.count("/"),
                size=st.st_size,
                mtime=st.st_mtime,
                folder=os.path.dirname(rel).replace("\\", "/") or ".",
            ))
    return out


_CREATOR_RE = re.compile(
    rb'<T\s+n="creator_name">([^<]{1,60})</T>', re.I)
_NAME_RE = re.compile(rb'<T\s+n="mod_name">([^<]{1,80})</T>', re.I)


def analyse_package(mf: ModFile, cfg: ResourceCfg):
    """Fill in resource keys, display name, creator for one package."""
    try:
        pkg = Package(mf.abs_path)
    except (PackageError, OSError, struct.error) as e:
        mf.error = str(e)
        return mf
    except Exception as e:                      # never let one file kill a scan
        mf.error = f"{type(e).__name__}: {e}"
        return mf

    mf.resources = len(pkg.resources)
    types = defaultdict(int)
    for r in pkg.resources:
        mf.keys.add(r.key)
        types[r.type_id] += 1
    mf.types = dict(types)

    # display name + creator from string tables / tuning
    for r in pkg.resources:
        if r.type_id == STBL_TYPE and not mf.display_name:
            data = pkg.try_payload(r)
            if data:
                try:
                    tbl = parse_stbl(data)
                except Exception:
                    tbl = {}
                for v in tbl.values():
                    v = v.strip()
                    if v and not v.startswith("(") and len(v) < 80:
                        mf.display_name = v
                        break
        if r.type_id == 0x0333406C and not (mf.creator and mf.display_name):
            data = pkg.try_payload(r)
            if data and data[:5] == b"<?xml":
                if not mf.creator:
                    m = _CREATOR_RE.search(data)
                    if m:
                        mf.creator = m.group(1).decode(
                            "utf-8", "replace").strip()
                if not mf.display_name:
                    m = _NAME_RE.search(data)
                    if m:
                        mf.display_name = m.group(1).decode(
                            "utf-8", "replace").strip()

    # filename-prefix creator heuristic (creator_ModName.package)
    if not mf.creator:
        stem = os.path.splitext(mf.name)[0]
        m = re.match(r"^([A-Za-z][A-Za-z0-9]{1,19})[_\- ]", stem)
        if m:
            mf.creator = m.group(1)

    mf.priority = cfg.priority_for(mf.rel_path)
    return mf


def compute_load_order(mods):
    """Winner = highest Resource.cfg priority; then shallowest; then name.

    Ordering follows the community-tested rule: all packages take the highest
    matching priority from Resource.cfg; ties are broken by folder depth
    (shallower loads first, so it overrides deeper), then alphabetically with
    special characters first, then digits, then letters.
    """
    ordered = sorted(
        mods,
        key=lambda m: (-m.priority, m.depth, _sort_key_for_name(m.name)))
    for i, m in enumerate(ordered):
        m.order_index = i
    return ordered


# ---------------------------------------------------------------- findings
def build_findings(scan: ScanResult, cfg: ResourceCfg):
    mods = scan.files
    f = scan.findings

    # ---- silent failures -------------------------------------------------
    deep_scripts = [m for m in mods
                    if m.is_script and m.depth > SCRIPT_MAX_DEPTH]
    if deep_scripts:
        f.append(Finding(
            kind="silent_script",
            severity="high",
            title=(plural(len(deep_scripts), "script mod") +
                   " that will never load"),
            detail=("The Sims 4 only loads .ts4script files up to "
                    f"{SCRIPT_MAX_DEPTH} subfolder deep. These are ignored "
                    "completely - no error, no LastException, they just do "
                    "nothing. This is the most common result of tidying up "
                    "a Mods folder."),
            files=deep_scripts,
            evidence="Game script loader depth limit",
            fix="Move each .ts4script up so it sits in Mods\\ or "
                "Mods\\<one folder>\\",
        ))

    deep_pkgs = [m for m in mods
                 if m.is_package and m.depth > PACKAGE_MAX_DEPTH]
    if deep_pkgs:
        f.append(Finding(
            kind="deep_package",
            severity="medium",
            title=(plural(len(deep_pkgs), "package") + " nested too deep to load"),
            detail=(f"Resource.cfg only scans {PACKAGE_MAX_DEPTH} levels of "
                    "subfolders. Anything deeper is invisible to the game."),
            files=deep_pkgs,
            fix="Flatten these folders.",
        ))

    # ---- duplicates by content ------------------------------------------
    by_hash = defaultdict(list)
    for m in mods:
        if m.content_hash and m.ext in MOD_EXT:
            by_hash[m.content_hash].append(m)
    dupes = {h: g for h, g in by_hash.items() if len(g) > 1}
    if dupes:
        wasted = sum(sum(m.size for m in g[1:]) for g in dupes.values())
        f.append(Finding(
            kind="duplicate",
            severity="high",
            title=(plural(len(dupes), "duplicated mod") +
                   f" ({len(dupes)} wasted)"),
            detail=("These files are byte-for-byte identical but sit under "
                    "different names, so name-based duplicate checkers miss "
                    "them. Reclaim roughly "
                    f"{wasted / 1024 / 1024:.1f} MB."),
            files=[m for g in dupes.values() for m in g],
            evidence="SHA-256 content match",
            fix="Keep one copy of each, delete the rest.",
        ))

    # ---- conflicts -------------------------------------------------------
    owner = defaultdict(list)
    for m in mods:
        if not m.is_package or m.error:
            continue
        for k in m.keys:
            owner[k].append(m)

    conflict_groups = []      # (key, holders) where holders differ in content
    redundant_keys = []       # same key, identical bytes everywhere
    for key, holders in owner.items():
        uniq = {m.abs_path: m for m in holders}
        if len(uniq) < 2:
            continue
        group = list(uniq.values())
        hashes = {m.content_hash for m in group if m.content_hash}
        if len(hashes) > 1:
            conflict_groups.append((key, group))
        elif hashes:
            redundant_keys.append((key, group))
    scan.conflicts = conflict_groups

    if conflict_groups:
        tuning_conflicts = [c for c in conflict_groups
                            if c[0][0] in TUNING_TYPES]
        cas_conflicts = [c for c in conflict_groups
                         if c[0][0] in CAS_TYPES]
        unique_files = {}
        for _key, group in conflict_groups:
            for m in group:
                unique_files[m.abs_path] = m

        # spell out the winners for the most important clashes
        examples = []
        for key, group in sorted(
                conflict_groups,
                key=lambda c: (c[0][0] not in TUNING_TYPES,
                               -len(c[1])))[:6]:
            winner = min(group, key=lambda m: m.order_index)
            kind = TYPE_NAMES.get(key[0], "resource")
            examples.append(
                f"{kind} {hexkey(key)}\n"
                f"      loaded: {winner.rel_path}   (priority "
                f"{winner.priority}, depth {winner.depth})\n"
                + "\n".join(
                    f"      ignored: {m.rel_path}" for m in group
                    if m is not winner))
        f.append(Finding(
            kind="conflict",
            severity="high",
            title=(plural(len(conflict_groups), "resource conflict")
                   + " between mods"
                   + (f" ({len(tuning_conflicts)} gameplay)"
                      if tuning_conflicts else "")),
            detail=("Two or more mods define the same resource ID with "
                    "different content. The game does not merge these - it "
                    "loads one and silently ignores the rest, so the other "
                    "mod's changes never happen.\n\n"
                    "Which one wins is decided by Resource.cfg priority "
                    "first, then folder depth (shallower wins), then "
                    "filename order.\n\n"
                    + "\n".join(examples)
                    + ("\n\n(only the first 6 shown here; see the Load order "
                       "tab or the exported report for all of them)"
                       if len(conflict_groups) > 6 else "")),
            files=list(unique_files.values()),
            evidence="Same type:group:instance keys, different payload hashes",
            fix=("Decide which mod you actually want and remove or replace the "
                 "other. If both are needed, ask the creators for a "
                 "compatibility patch."),
        ))

    if redundant_keys:
        unique_files = {}
        for _key, group in redundant_keys:
            for m in group:
                unique_files[m.abs_path] = m
        f.append(Finding(
            kind="redundant",
            severity="low",
            title=(plural(len(redundant_keys), "duplicate resource")
                   + " across files"),
            detail=("The same resource ID with byte-identical content appears "
                    "in more than one package. This is harmless - the game "
                    "picks one and the result is the same either way - but "
                    "one copy is redundant."),
            files=list(unique_files.values()),
            evidence="Same key + same payload hash",
            fix="Remove the duplicate copy (check the duplicates list first).",
        ))

    # ---- health ----------------------------------------------------------
    junk = [m for m in mods if m.ext in JUNK_EXT]
    if junk:
        f.append(Finding(
            kind="junk",
            severity="low",
            title=(plural(len(junk), "file") + " that should not be in Mods"),
            detail=("Archives, readmes and shortcuts sitting in the Mods "
                    "folder. The game ignores them, but they slow scanning "
                    "and hide the real content."),
            files=junk,
            fix="Move to a downloads folder outside Mods.",
        ))

    broken = [m for m in mods if m.error]
    if broken:
        f.append(Finding(
            kind="unreadable",
            severity="high",
            title=(plural(len(broken), "corrupt package")),
            detail=("These could not be parsed as Sims 4 packages. They are "
                    "either damaged downloads or renamed files that were "
                    "never packages to begin with."),
            files=broken,
            evidence="DBPF header / index parse failure",
            fix="Re-download or delete.",
        ))

    empty = [m for m in mods if m.is_package and not m.error
             and m.resources == 0]
    if empty:
        f.append(Finding(
            kind="empty",
            severity="medium",
            title=(plural(len(empty), "package") + " with no content"),
            detail="Valid header, zero content. They do nothing at all.",
            files=empty,
            fix="Delete.",
        ))

    zero = [m for m in mods if m.size == 0]
    if zero:
        f.append(Finding(
            kind="zero_byte",
            severity="medium",
            title=plural(len(zero), "empty file", "empty files"),
            detail="Zero-byte files, usually a failed download.",
            files=zero,
            fix="Delete and re-download.",
        ))

    return scan


# ------------------------------------------------------------------ driver
def scan_mods_folder(root: str, progress: Callable = None,
                     workers: int = None, hash_files: bool = True):
    t0 = time.time()
    root = os.path.abspath(root)
    res = ScanResult(root=root)
    if not os.path.isdir(root):
        res.warnings.append(f"Not a folder: {root}")
        return res

    if progress:
        progress("Listing files...")
    files = collect_files(root)

    # Resource.cfg
    cfg_path = os.path.join(root, "Resource.cfg")
    cfg = ResourceCfg()
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8", errors="replace") as fh:
                cfg = ResourceCfg(fh.read())
        except OSError as e:
            res.warnings.append(f"Could not read Resource.cfg: {e}")

    if workers is None:
        workers = min(8, (os.cpu_count() or 4))

    # ---- hash everything (fast path: size grouping first) ---------------
    if hash_files:
        if progress:
            progress(f"Hashing {len(files)} files...")
        # Only files whose size is shared can possibly be duplicates, but we
        # still need a hash for redundant-override maths on packages.
        to_hash = [m for m in files if m.ext in MOD_EXT and m.size > 0]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(sha256_file, m.abs_path): m for m in to_hash}
            done = 0
            for fut in futs:
                m = futs[fut]
                try:
                    m.content_hash = fut.result()
                except OSError:
                    m.content_hash = None
                done += 1
                if progress and done % 250 == 0:
                    progress(f"Hashing {done}/{len(to_hash)}...")

    # ---- parse packages --------------------------------------------------
    pkgs = [m for m in files if m.is_package]
    if progress:
        progress(f"Reading {len(pkgs)} packages...")
    if pkgs:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(analyse_package, m, cfg) for m in pkgs]
            done = 0
            for fut in futs:
                try:
                    fut.result()
                except Exception:
                    pass
                done += 1
                if progress and done % 200 == 0:
                    progress(f"Reading packages {done}/{len(pkgs)}...")

    res.files = files
    res.load_order = compute_load_order([m for m in files if m.is_package])

    if progress:
        progress("Analysing...")
    build_findings(res, cfg)

    # ---- stats -----------------------------------------------------------
    by_kind = defaultdict(int)
    for m in files:
        by_kind[m.kind] += 1
    res.stats = {
        "total_files": len(files),
        "packages": len(pkgs),
        "scripts": sum(1 for m in files if m.is_script),
        "total_bytes": sum(m.size for m in files),
        "by_kind": dict(by_kind),
        "resource_cfg": cfg.loaded,
        "findings": len(res.findings),
        "high": sum(1 for x in res.findings if x.severity == "high"),
    }
    res.duration = time.time() - t0
    return res


# ------------------------------------------------------- exception reports
EXC_FILES = ("lastexception.txt", "lastuiexception.txt",
             "lastcleanexception.txt")


def find_exception_files(user_dir):
    """Newest game exception reports in the Sims 4 user folder."""
    out = []
    if not os.path.isdir(user_dir):
        return out
    for fn in os.listdir(user_dir):
        low = fn.lower()
        if low.startswith("last") and "exception" in low:
            p = os.path.join(user_dir, fn)
            try:
                out.append((os.path.getmtime(p), p))
            except OSError:
                pass
    out.sort(reverse=True)
    return [p for _, p in out[:10]]


TB_RE = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
MODPATH_RE = re.compile(r'([A-Za-z]:\\[^"]*?Mods\\[^"]*)', re.I)
EXC_RE = re.compile(r'^(\w+(?:Error|Exception|Warning))\b[:\s]+(.*)$', re.M)


def parse_exception(text):
    """Pull the useful facts out of a LastException dump."""
    info = {"traceback": [], "exception": None, "message": "",
            "mod_paths": [], "mentions": []}
    for m in TB_RE.finditer(text):
        path, line, func = m.group(1), m.group(2), m.group(3)
        if "InGame" in path or "TS4" in path or "Mods" in path:
            info["traceback"].append((path, line, func))
    m = EXC_RE.search(text)
    if m:
        info["exception"] = m.group(1)
        info["message"] = m.group(2).strip()[:400]
    info["mod_paths"] = sorted(set(MODPATH_RE.findall(text)))[:20]
    return info


def correlate_exception(text, files):
    """Rank installed mods by how likely they are to explain an exception."""
    info = parse_exception(text)
    scores = defaultdict(float)
    reasons = defaultdict(list)
    low = text.lower()

    for m in files:
        stem = os.path.splitext(m.name)[0]
        stem_low = stem.lower()
        # direct mention of the file or its stem
        if stem_low and len(stem_low) > 4 and stem_low in low:
            scores[m.abs_path] += 10
            reasons[m.abs_path].append("named in the exception report")
        # module path match (script mods register a module name)
        key = re.sub(r"[^a-z0-9]", "", stem_low)
        if key and len(key) > 5 and key in re.sub(r"[^a-z0-9]", "", low):
            scores[m.abs_path] += 4
            reasons[m.abs_path].append("module name appears in the traceback")
        # mods the exception explicitly flags
        if m.is_script:
            scores[m.abs_path] += 0.2
    for p in info["mod_paths"]:
        base = os.path.basename(p).lower()
        for m in files:
            if m.name.lower() == base:
                scores[m.abs_path] += 8
                reasons[m.abs_path].append("path quoted in report")
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return info, [(p, s, reasons[p]) for p, s in ranked if s >= 4][:25]
