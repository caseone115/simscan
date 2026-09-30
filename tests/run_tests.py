"""SimScan test suite.

Runs on plain stdlib + Pillow. Builds its own fixtures from committed sample
packages where available, and synthesises DBPF packages where it needs
controlled resource keys.

    python tests/run_tests.py
"""
import io
import os
import shutil
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from simscan import __version__, analyzer, dbpf, dds, recyclex, report  # noqa: E402

SAMPLES = os.path.join(ROOT, "build", "samples")
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    mark = "ok  " if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail and not cond
                                  else ""))


# --------------------------------------------------------------- DBPF writer
def write_package(path, resources):
    """Minimal uncompressed DBPF 2.1 writer for controlled fixtures."""
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
    with open(path, "wb") as fh:
        fh.write(buf)
    return path


def write_stbl(texts):
    """Build a STBL v5 resource (UTF-8 strings)."""
    body = bytearray()
    for key, s in texts:
        b = s.encode("utf-8")
        body += struct.pack("<I", key) + b"\x00" + struct.pack("<H", len(b)) + b
    hdr = bytearray(0x15)
    hdr[0:4] = b"STBL"
    struct.pack_into("<H", hdr, 4, 5)          # version
    hdr[6] = 0                                 # compression
    struct.pack_into("<H", hdr, 7, len(texts))  # entry count
    return bytes(hdr) + bytes(body)


def mk_dds(w, h, fourcc, payload):
    """Build a DDS blob.

    Layout is 4-byte magic 'DDS ' followed by a 124-byte header, so the
    pixel data starts at offset 128. Field offsets inside the header mirror
    the real files: dwSize 0, dwFlags 4, height 8, width 12, pfSize 72,
    pfFlags 76, fourCC 80 (i.e. 84..88 in absolute file offsets).
    """
    hdr = bytearray(124)
    struct.pack_into("<I", hdr, 0, 124)          # dwSize
    struct.pack_into("<I", hdr, 4, 0x1007)       # dwFlags
    struct.pack_into("<II", hdr, 8, h, w)        # dwHeight, dwWidth
    struct.pack_into("<I", hdr, 16, 0)           # pitch
    struct.pack_into("<I", hdr, 24, 1)           # mip count
    struct.pack_into("<I", hdr, 72, 32)          # pfSize
    struct.pack_into("<I", hdr, 76, 4)           # DDPF_FOURCC
    hdr[80:84] = fourcc
    return b"DDS " + bytes(hdr) + payload


# --------------------------------------------------------------------- tests
def test_dbpf_roundtrip(tmp):
    print("\nDBPF reader")
    key = (0x545AC67A, 0x00000000, 0x2F1A3C4D5E6F7788)
    p = write_package(os.path.join(tmp, "a.package"), [(key, b"hello-world")])
    pkg = dbpf.Package(p)
    check("reads header version 2.1", pkg.version == "2.1", pkg.version)
    check("indexes one resource", len(pkg.resources) == 1)
    check("resource key round-trips", pkg.resources[0].key == key,
          str(pkg.resources[0].key))
    check("payload round-trips", pkg.payload(pkg.resources[0]) == b"hello-world")

    # multi-resource
    p2 = write_package(os.path.join(tmp, "b.package"), [
        ((0x034AEECB, 0, 1), b"x"), ((0x00B2D882, 0, 2), b"yy")])
    pkg2 = dbpf.Package(p2)
    check("indexes two resources", len(pkg2.resources) == 2, str(len(pkg2.resources)))

    # non-DBPF
    bad = os.path.join(tmp, "bad.package")
    open(bad, "wb").write(b"NOPE" + b"\x00" * 200)
    try:
        dbpf.Package(bad)
        check("rejects non-DBPF", False, "no exception")
    except dbpf.PackageError:
        check("rejects non-DBPF", True)
    except Exception as e:
        check("rejects non-DBPF", False, f"{type(e).__name__}")

    # truncated / corrupt payload must raise, not crash the scan
    trunc = os.path.join(tmp, "trunc.package")
    data = bytearray(open(p, "rb").read())
    data[96:106] = b"\x00" * 10
    open(trunc, "wb").write(bytes(data))
    try:
        pk = dbpf.Package(trunc)
        r = pk.resources[0] if pk.resources else None
        ok = True
        if r:
            try:
                pk.payload(r)
            except dbpf.PackageError:
                pass
        check("survives corrupt payload", ok)
    except Exception as e:
        check("survives corrupt payload", False, f"{type(e).__name__}")


def test_stbl(tmp):
    print("\nString tables (real packages)")
    sample = os.path.join(SAMPLES, "simmertales_a.package")
    if not os.path.isfile(sample):
        # Third-party mod packages are not redistributed with this repo, so
        # this check only runs when samples are present locally.
        print("  [skip] real-package STBL check (no build/samples present)")
        blob = write_stbl([(0x1234, "Hello World"), (0x5678, "Second")])
        got = dbpf.parse_stbl(blob)
        check("STBL round-trip (synthetic)", got.get(0x1234) == "Hello World",
              str(got))
        return
    pkg = dbpf.Package(sample)
    names = []
    for r in pkg.resources:
        if r.type_id == 0x220557DA:
            try:
                names = list(dbpf.parse_stbl(pkg.payload(r)).values())
            except Exception:
                continue
            if names:
                break
    check("extracts human-readable name from STBL",
          any("Bacon" in n for n in names), str(names[:2]))

    # synthetic round-trip proves the layout we write and read agrees
    blob = write_stbl([(0x1234, "Hello World"), (0x5678, "Second")])
    got = dbpf.parse_stbl(blob)
    check("STBL round-trip", got.get(0x1234) == "Hello World", str(got))


def test_dds():
    print("\nDDS / DXT decoder (synthetic ground truth)")
    rgba, w, h = dds.dds_to_rgba(
        mk_dds(4, 4, b"DXT1", struct.pack("<HHI", 0xF800, 0x001F, 0)))
    check("DXT1 index 0 -> red", tuple(rgba[:4]) == (255, 0, 0, 255),
          str(tuple(rgba[:4])))
    rgba, _, _ = dds.dds_to_rgba(
        mk_dds(4, 4, b"DXT1", struct.pack("<HHI", 0xF800, 0x001F, 0x55555555)))
    check("DXT1 index 1 -> blue", tuple(rgba[:4]) == (0, 0, 255, 255),
          str(tuple(rgba[:4])))
    rgba, _, _ = dds.dds_to_rgba(
        mk_dds(4, 4, b"DXT1", struct.pack("<HHI", 0xF800, 0x001F, 0xAAAAAAAA)))
    check("DXT1 index 2 -> 2/3 blend", tuple(rgba[:4]) == (170, 0, 85, 255),
          str(tuple(rgba[:4])))

    blk = bytes([255, 255]) + (0).to_bytes(6, "little") + \
        struct.pack("<HHI", 0xF800, 0x001F, 0)
    rgba, _, _ = dds.dds_to_rgba(mk_dds(4, 4, b"DST5", blk))
    check("DST5 maps to DXT5, opaque", tuple(rgba[:4]) == (255, 0, 0, 255),
          str(tuple(rgba[:4])))

    blk = bytes([0, 0]) + (0).to_bytes(6, "little") + \
        struct.pack("<HHI", 0xF800, 0x001F, 0)
    rgba, _, _ = dds.dds_to_rgba(mk_dds(4, 4, b"DST5", blk))
    check("DST5 alpha 0 -> transparent", rgba[3] == 0, str(rgba[3]))

    b1 = struct.pack("<HHI", 0xF800, 0x001F, 0)
    b2 = struct.pack("<HHI", 0x07E0, 0x001F, 0)
    rgba, w, h = dds.dds_to_rgba(mk_dds(8, 4, b"DXT1", b1 + b2))
    left = tuple(rgba[0:4]); right = tuple(rgba[16:20])
    check("multi-block placement", left == (255, 0, 0, 255)
          and right == (0, 255, 0, 255), f"{left} {right}")

    try:
        dds.dds_to_rgba(b"DDS " + b"\x00" * 200)
        check("rejects unsupported format", False, "no exception")
    except dds.DdsError:
        check("rejects unsupported format", True)
    except Exception as e:
        check("rejects unsupported format", False, type(e).__name__)


def test_analysis(tmp):
    print("\nAnalysis engine")
    root = os.path.join(tmp, "Mods")
    os.makedirs(os.path.join(root, "[MOD] PackA"), exist_ok=True)
    os.makedirs(os.path.join(root, "Deep/Inner/MCCC"), exist_ok=True)
    os.makedirs(os.path.join(root, "Junk"), exist_ok=True)

    # conflict: same key, different content
    K = (0x545AC67A, 0, 0x1111222233334444)
    write_package(os.path.join(root, "[MOD] PackA", "ModA.package"), [(K, b"A")])
    write_package(os.path.join(root, "[MOD] PackA", "ModB.package"), [(K, b"B")])

    # duplicate: identical content, different names/folders
    K2 = (0x034AEECB, 0, 0xAAAABBBBCCCCDDDD)
    dup_src = write_package(os.path.join(root, "Dup1.package"), [(K2, b"mesh")])
    shutil.copy(dup_src, os.path.join(root, "[MOD] PackA", "Dup1 (1).package"))

    # redundant: same key AND same content inside two packages
    K3 = (0x00B2D882, 0, 0x0F0F0F0F0F0F0F0F)
    write_package(os.path.join(root, "[MOD] PackA", "R1.package"), [(K3, b"same")])
    write_package(os.path.join(root, "[MOD] PackA", "R2.package"), [(K3, b"same")])

    # silent failure: ts4script two folders deep
    open(os.path.join(root, "Deep/Inner/MCCC/script.ts4script"), "wb").write(b"PK")
    # junk
    open(os.path.join(root, "Junk/readme.txt"), "w").write("hi")
    open(os.path.join(root, "Junk/archive.zip"), "wb").write(b"PK")
    # empty + zero byte
    open(os.path.join(root, "empty.package"), "wb").write(b"DBPF" + b"\x00" * 92)
    open(os.path.join(root, "zero.package"), "wb").write(b"")

    res = analyzer.scan_mods_folder(root)
    kinds = {f.kind: f for f in res.findings}

    check("flags silent script-death", "silent_script" in kinds)
    check("names the buried script",
          kinds.get("silent_script") and any(
              "script.ts4script" in m.rel_path
              for m in kinds["silent_script"].files))
    check("detects content duplicates", "duplicate" in kinds)
    check("conflict detected", "conflict" in kinds)
    check("conflict names a winner",
          kinds.get("conflict") and "loaded:" in kinds["conflict"].detail)
    check("redundant overrides detected", "redundant" in kinds)
    check("junk detected", "junk" in kinds)
    check("empty package detected", "empty" in kinds)
    check("zero-byte file detected", "zero_byte" in kinds)
    check("corrupt package flagged", "unreadable" in kinds,
          str([m.rel_path for m in kinds.get("unreadable", type(
              'x', (), {'files': []})).files]))
    check("load order computed", len(res.load_order) >= 4,
          str(len(res.load_order)))
    check("stats populated", res.stats.get("total_files", 0) >= 9,
          str(res.stats.get("total_files")))


def test_conflict_winner(tmp):
    print("\nConflict winner (Resource.cfg precedence)")
    root = os.path.join(tmp, "Cfg")
    os.makedirs(os.path.join(root, "Overrides"), exist_ok=True)
    os.makedirs(os.path.join(root, "Normal"), exist_ok=True)
    K = (0x545AC67A, 0, 0x9999888877776666)
    write_package(os.path.join(root, "Normal", "z_Mod.package"), [(K, b"normal")])
    write_package(os.path.join(root, "Overrides", "a_Mod.package"), [(K, b"over")])
    with open(os.path.join(root, "Resource.cfg"), "w") as fh:
        fh.write("Priority 1000\nPackedFile Overrides/*.package\n"
                 "Priority 500\nPackedFile Normal/*.package\n")

    res = analyzer.scan_mods_folder(root)
    conf = next((f for f in res.findings if f.kind == "conflict"), None)
    check("conflict found with Resource.cfg", conf is not None)
    if conf:
        check("higher Resource.cfg priority wins",
              "Overrides" in conf.detail.split("loaded:")[1].split("\n")[0],
              conf.detail[:200])
    ovr = [m for m in res.load_order if "Overrides" in m.rel_path]
    nrm = [m for m in res.load_order if "Normal" in m.rel_path]
    check("priority parsed from Resource.cfg",
          ovr and nrm and ovr[0].priority == 1000 and nrm[0].priority == 500,
          f"{ovr[0].priority if ovr else '?'} / {nrm[0].priority if nrm else '?'}")


def test_disable_undo(tmp):
    print("\nDisable / undo round-trip")
    root = os.path.join(tmp, "Dis")
    os.makedirs(root, exist_ok=True)
    f = os.path.join(root, "mod.package")
    write_package(f, [((0x034AEECB, 0, 1), b"x")])
    files = analyzer.collect_files(root)
    check("file collected", len(files) == 1)

    batch = recyclex.disable_files(root, files)
    check("file moved to _disabled", len(batch) == 1)
    check("original gone", not os.path.exists(f))
    check("copy exists in _disabled",
          os.path.exists(os.path.join(root, "_disabled", "mod.package")))
    check("undo available", recyclex.has_undo(root))

    n = recyclex.undo_last_disable(root)
    check("undo restored the file", n == 1 and os.path.exists(f),
          f"n={n} exists={os.path.exists(f)}")
    check("undo log cleared", not recyclex.has_undo(root))


def test_reports(tmp):
    print("\nReports")
    root = os.path.join(tmp, "Rep")
    os.makedirs(root, exist_ok=True)
    K = (0x545AC67A, 0, 5)
    write_package(os.path.join(root, "a.package"), [(K, b"a")])
    write_package(os.path.join(root, "b.package"), [(K, b"b")])
    res = analyzer.scan_mods_folder(root)

    for fn, writer in (("r.html", report.to_html), ("r.csv", report.to_csv),
                       ("r.json", report.to_json), ("r.txt", report.to_text)):
        p = os.path.join(tmp, fn)
        writer(res, p)
        check(f"wrote {fn}", os.path.getsize(p) > 50,
              str(os.path.getsize(p)))

    # The published sample report is a real to_html() output, and the landing
    # page invites a buyer to open it. Nothing asserted what was IN it, so it
    # shipped as a dead end: no link home, no way to buy. Assert the two links
    # now, because the page that promises "a real report, not a mock-up" has to
    # be a page a reader can leave.
    html = open(os.path.join(tmp, "r.html")).read()
    check("report links the SimScan home page",
          'https://caseone115.github.io/simscan/' in html)
    check("report links the shop", "https://teeterbot.gumroad.com/l/simscan" in html)
    check("report footer names the installed version", __version__ in html)

    import json
    data = json.load(open(os.path.join(tmp, "r.json")))
    check("json is parseable and has findings", len(data["findings"]) >= 1)
    check("json records files", len(data["files"]) == 2)

    # 50/50 plan
    p = os.path.join(tmp, "plan.txt")
    report.to_50_50_plan(res, p, ["a.package", "b.package"])
    txt = open(p).read()
    check("50/50 plan written", "50/50" in txt and "a.package" in txt)
    check("plan states it cannot test for you",
          "cannot" in txt.lower() or "not" in txt.lower())


def test_exception(tmp):
    print("\nLastException correlation")
    root = os.path.join(tmp, "Exc")
    os.makedirs(root, exist_ok=True)
    write_package(os.path.join(root, "mccc_extra.package"), [((1, 0, 1), b"z")])
    open(os.path.join(root, "unrelated_mod.package"), "wb").write(
        b"DBPF" + b"\x00" * 92)

    le = os.path.join(tmp, "lastException.txt")
    open(le, "w").write(
        'Traceback (most recent call last):\n'
        '  File "T:\\InGame\\Gameplay\\Scripts\\Server\\foo.py", line 10, '
        'in bar\n'
        'ValueError: something broke in mccc_extra module\n')
    text = open(le).read()
    info, ranked = analyzer.correlate_exception(
        text, analyzer.collect_files(root))
    check("parses exception type", info.get("exception") == "ValueError",
          str(info.get("exception")))
    check("ranks the mentioned mod first",
          ranked and "mccc_extra" in ranked[0][0], str(ranked[:1]))


def test_version_surfaces():
    """Every surface that states a version must state the same one.

    Added 2026-09-30: the v1.0.1 release shipped an installer named
    SimScan-1.0.0-Setup.exe whose own resource said 1.0.0 and whose uninstall
    entry wrote DisplayVersion 1.0.0. Nothing in the suite noticed, because
    nothing in the suite knew a version had more than one surface. The assertion
    itself lives in scripts/check_version_consistency.py (it also reads a built
    artifact's own PE resource, which needs a build), so this drives that.
    """
    print("\nVersion surfaces")
    import subprocess
    script = os.path.join(ROOT, "scripts", "check_version_consistency.py")
    r = subprocess.run([sys.executable, script], capture_output=True, text=True,
                       cwd=ROOT)
    detail = (r.stdout or "").strip().splitlines()
    tail = " | ".join(detail[-3:])[:300]
    check("every version surface agrees", r.returncode == 0, tail)

    # And the accessor must survive a same-length version bump, which defeats
    # CPython's bytecode-cache check (mtime + size): observed for real here.
    acc = os.path.join(ROOT, "scripts", "version.py")
    r2 = subprocess.run([sys.executable, acc, "--check"], capture_output=True,
                        text=True, cwd=ROOT)
    check("the version accessor agrees with an import",
          r2.returncode == 0, (r2.stdout or "").strip()[-200:])


def test_winget_manifest():
    """The winget manifest must agree with the source, and the check must fail.

    Added 2026-09-30 alongside the manifest itself. Work-queue item 15
    (submitting SimScan to microsoft/winget-pkgs) was blocked on the installer
    disagreeing with itself about its version, which v1.0.2 fixed. This keeps
    the manifest from drifting the same way: the structure check is offline,
    and the fault injection restores a real drift and requires a refusal, so
    the guard has been seen to fail rather than only to pass.
    """
    print("\nwinget manifest")
    import subprocess
    import yaml
    chk = os.path.join(ROOT, "scripts", "check_winget_manifest.py")
    r = subprocess.run([sys.executable, chk], capture_output=True, text=True, cwd=ROOT)
    tail = (r.stdout or "").strip().splitlines()
    check("winget manifest passes its own check", r.returncode == 0,
          (tail[-1][:220] if tail else ""))

    from simscan import __version__ as v
    base = os.path.join(ROOT, "winget", "manifests", "s", "SimScan", "SimScan", v)
    check("winget manifest exists for the shipped version", os.path.isdir(base), base)

    ins = os.path.join(base, "SimScan.SimScan.installer.yaml")
    if not os.path.isfile(ins):
        check("winget installer manifest is present", False, ins)
        return
    original = open(ins).read()
    try:
        doc = yaml.safe_load(original)
        doc["PackageVersion"] = "0.0.0"
        open(ins, "w").write(yaml.safe_dump(doc, sort_keys=False))
        r2 = subprocess.run([sys.executable, chk], capture_output=True, text=True, cwd=ROOT)
        tail2 = (r2.stdout or "").strip().splitlines()
        check("winget manifest check refuses a drifted version", r2.returncode != 0,
              (tail2[-1][:220] if tail2 else ""))
    finally:
        open(ins, "w").write(original)


def main():
    print("=" * 68)
    print("SimScan test suite")
    print("=" * 68)
    tmp = tempfile.mkdtemp(prefix="simscan-test-")
    try:
        test_dbpf_roundtrip(tmp)
        test_stbl(tmp)
        test_dds()
        test_analysis(tmp)
        test_conflict_winner(tmp)
        test_disable_undo(tmp)
        test_reports(tmp)
        test_exception(tmp)
        test_version_surfaces()
        test_winget_manifest()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 68)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"    FAILED: {f}")
    print("=" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
