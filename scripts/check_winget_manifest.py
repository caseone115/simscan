#!/usr/bin/env python3
"""Guard the winget submission before it is offered to microsoft/winget-pkgs.

The manifest is not hand-written truth. It makes three promises a moderator
checks mechanically - the version, the installer URL, and the installer hash -
and this script asserts all three against the *published* release rather than
against the build log, in the same spirit as check_version_consistency.py.

    python scripts/check_winget_manifest.py             # structure only
    python scripts/check_winget_manifest.py --release   # + fetch SHA256SUMS.txt

Added 2026-09-30. Work-queue item 15 was unblocked when v1.0.2 made the
installer agree with itself about its own version; this is what stops the
manifest drifting from the release the way the release itself once drifted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
IDENT = "SimScan.SimScan"
MV = "1.12.0"
LOCALE = "en-US"
REPO = "caseone115/simscan"
HEX64 = re.compile(r"^[0-9A-F]{64}$")

problems = []


def fail(msg):
    problems.append(msg)
    print("  FAIL", msg)


def ok(msg):
    print("  ok  ", msg)


def source_version():
    lines = []
    with open(ROOT / "simscan" / "__init__.py") as fh:
        lines = list(fh)
    txt = "".join(lines)
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', txt, re.M)
    if not m:
        fail("could not parse __version__ out of simscan/__init__.py")
        return None
    return m.group(1)


def load(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def sha_from_release(version, exe_name):
    url = "https://github.com/%s/releases/download/v%s/SHA256SUMS.txt" % (REPO, version)
    with urllib.request.urlopen(url, timeout=60) as resp:
        body = "".join(line.decode() for line in resp)
    for line in body.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].strip() == exe_name:
            return parts[0].upper()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", action="store_true",
                    help="fetch the published SHA256SUMS.txt and compare hashes")
    args = ap.parse_args()

    version = source_version()
    if version is None:
        return 1
    ok("source version is %s" % version)

    base = ROOT / "winget" / "manifests" / "s" / "SimScan" / "SimScan" / version
    if not base.is_dir():
        fail("manifest directory missing: %s" % base)
        return 1
    ok("manifest directory exists")

    ver_f = base / (IDENT + ".yaml")
    loc_f = base / (IDENT + ".locale." + LOCALE + ".yaml")
    ins_f = base / (IDENT + ".installer.yaml")
    for p in (ver_f, loc_f, ins_f):
        if not p.is_file():
            fail("missing file %s" % p.name)
            return 1
    ok("all three manifest files present")

    ver = load(ver_f)
    loc = load(loc_f)
    ins = load(ins_f)

    for name, doc in (("version", ver), ("locale", loc), ("installer", ins)):
        if doc.get("ManifestVersion") != MV:
            fail("%s: ManifestVersion is %r, expected %s" % (name, doc.get("ManifestVersion"), MV))
        if doc.get("ManifestType") != name:
            fail("%s: ManifestType is %r" % (name, doc.get("ManifestType")))
        if doc.get("PackageIdentifier") != IDENT:
            fail("%s: PackageIdentifier is %r" % (name, doc.get("PackageIdentifier")))
        if doc.get("PackageVersion") != version:
            fail("%s: PackageVersion %r != source %r" % (name, doc.get("PackageVersion"), version))
    if ver.get("DefaultLocale") != LOCALE:
        fail("version: DefaultLocale is %r" % ver.get("DefaultLocale"))
    ok("identifiers, versions and manifest types agree")

    for key in ("Publisher", "PackageName", "ShortDescription", "License", "LicenseUrl", "PackageUrl", "Tags"):
        if not loc.get(key):
            fail("locale: %s is empty" % key)
    if str(loc.get("License", "")).upper() != "MIT":
        fail("locale: License is %r, the repo LICENSE is MIT" % loc.get("License"))
    ok("locale carries the fields a listing needs")

    if ins.get("InstallerType") != "inno":
        fail("installer: InstallerType is %r, the setup is Inno Setup" % ins.get("InstallerType"))
    if ins.get("Scope") != "user":
        fail("installer: Scope is %r, the .iss sets PrivilegesRequired=lowest" % ins.get("Scope"))

    entries = ins.get("Installers") or []
    if len(entries) != 1:
        fail("installer: expected exactly 1 installer entry, found %d" % len(entries))
    for e in entries:
        if e.get("Architecture") != "x64":
            fail("installer: Architecture %r" % e.get("Architecture"))
        want = "https://github.com/%s/releases/download/v%s/SimScan-%s-Setup.exe" % (REPO, version, version)
        if e.get("InstallerUrl") != want:
            fail("installer: InstallerUrl is %r, expected %r" % (e.get("InstallerUrl"), want))
        sha = str(e.get("InstallerSha256", ""))
        if not HEX64.match(sha):
            fail("installer: InstallerSha256 %r is not 64 upper-case hex" % sha)
        if e.get("InstallerUrl") and "gumroad.com" in e.get("InstallerUrl"):
            fail("installer: URL points at the paid listing - winget policy requires "
                 "an installer URL discoverable from the publisher, and a paywalled "
                 "URL makes `winget install` fail for anyone who has not paid")
    ok("installer entry points at the public release and is x64")

    af = ins.get("AppsAndFeaturesEntries") or []
    if not af:
        fail("installer: AppsAndFeaturesEntries missing - winget reads the installed "
             "DisplayVersion back, which is the check the v1.0.1 drift failed")
    for a in af:
        if a.get("DisplayVersion") != version:
            fail("installer: AppsAndFeaturesEntries DisplayVersion %r != %r" % (a.get("DisplayVersion"), version))
    ok("AppsAndFeaturesEntries asserts DisplayVersion %s" % version)

    if args.release:
        try:
            published = sha_from_release(version, "SimScan-%s-Setup.exe" % version)
        except Exception as exc:  # network is not this script's job to fix
            fail("could not fetch the published SHA256SUMS.txt: %r" % exc)
            published = None
        if published is None:
            fail("published SHA256SUMS.txt has no line for SimScan-%s-Setup.exe" % version)
        else:
            mine = str(entries[0].get("InstallerSha256", "")).upper()
            if mine != published:
                fail("manifest hash %s != published hash %s" % (mine, published))
            else:
                ok("manifest hash matches the published SHA256SUMS.txt (%s)" % published)
    else:
        print("  --  --release not given: hash not compared against the published sums")

    if problems:
        print("FAILED: %d problem(s)" % len(problems))
        return 1
    print("PASS: the winget manifest agrees with the release it points at")
    return 0


if __name__ == "__main__":
    sys.exit(main())
