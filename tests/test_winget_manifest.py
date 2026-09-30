#!/usr/bin/env python3
"""Prove check_winget_manifest.py can fail.

A guard that has only ever been seen to pass is not a guard. Each case below
restores a *real* fault this manifest could carry, runs the checker as a
subprocess, and requires a non-zero exit. Then the clean manifest must pass.

One case - a well-formed but wrong SHA256 - can only be decided against the
published sums, so it runs the checker with --release and therefore needs the
network. It is called out rather than quietly folded in: the first version of
this file ran every case offline and reported 7/8, and the missing one was the
test's fault, not the checker's.

    python tests/test_winget_manifest.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "winget" / "manifests" / "s" / "SimScan" / "SimScan" / "1.0.2"
INS = BASE / "SimScan.SimScan.installer.yaml"
CHECK = ROOT / "scripts" / "check_winget_manifest.py"


def run(release=False):
    cmd = [sys.executable, str(CHECK)]
    if release:
        cmd.append("--release")
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def mutate(path, fn):
    original = path.read_text()
    doc = yaml.safe_load(original)
    fn(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return original


def restore(path, original):
    path.write_text(original)


CASES = []


def case(name, path, fn, release=False):
    CASES.append((name, path, fn, release))


def wrong_version(d):
    d["PackageVersion"] = "1.0.1"


def gumroad_url(d):
    d["Installers"][0]["InstallerUrl"] = (
        "https://teeterbot.gumroad.com/l/simscan/download")
    d["Installers"][0]["InstallerSha256"] = "A" * 64


def wrong_hash(d):
    d["Installers"][0]["InstallerSha256"] = "B" * 64


def lower_hash(d):
    d["Installers"][0]["InstallerSha256"] = d["Installers"][0]["InstallerSha256"].lower()


def no_af(d):
    d.pop("AppsAndFeaturesEntries", None)


def wrong_display(d):
    d["AppsAndFeaturesEntries"][0]["DisplayVersion"] = "1.0.0"


def wrong_scope(d):
    d["Scope"] = "machine"


def wrong_type(d):
    d["InstallerType"] = "nullsoft"


case("PackageVersion drifts from the source", INS, wrong_version)
case("InstallerUrl points at the paid Gumroad listing", INS, gumroad_url)
case("InstallerSha256 is wrong but well-formed (needs --release)", INS, wrong_hash, release=True)
case("InstallerSha256 is lower-case (schema wants upper)", INS, lower_hash)
case("AppsAndFeaturesEntries removed", INS, no_af)
case("DisplayVersion restored to the 1.0.0 drift", INS, wrong_display)
case("Scope says machine, the setup installs per-user", INS, wrong_scope)
case("InstallerType is not inno", INS, wrong_type)


def main():
    caught = 0
    for name, path, fn, release in CASES:
        original = mutate(path, fn)
        try:
            rc, out = run(release=release)
        finally:
            restore(path, original)
        if rc != 0:
            caught += 1
            print("  caught  %s" % name)
        else:
            print("  MISSED  %s" % name)
    rc, out = run(release=True)
    print("clean manifest exit=%d" % rc)
    total = len(CASES)
    print("caught %d/%d planted faults; clean run %s" %
          (caught, total, "PASSES" if rc == 0 else "FAILS"))
    if caught != total or rc != 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
