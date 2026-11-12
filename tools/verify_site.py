#!/usr/bin/env python3
"""Check a site that tools/publish.sh signed, before it is pushed and deployed.

Usage:
  tools/verify_site.py SITE --floor VERSION

Fails unless index.json.sig is a signature of index.json by keys/current.pub or keys/next.pub,
the index version is higher than VERSION, the version on gh-pages, and the site holds exactly
the files that the index lists with their SHA-256, the schemas of this checkout, CNAME, and
.nojekyll. Needs only the standard library and openssl, so the push job installs nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ("keys/current.pub", "keys/next.pub")
CNAME = b"extensions.monetenapp.com\n"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_files(site: Path) -> tuple[dict[str, Path], list[str]]:
    """Maps each regular file to its path, and lists every entry that is neither a file nor a folder."""
    files, irregular = {}, []
    for parent, dirs, names in os.walk(site):
        for name in dirs + names:
            path = Path(parent, name)
            mode = path.lstat().st_mode
            if stat.S_ISREG(mode):
                files[path.relative_to(site).as_posix()] = path
            elif not stat.S_ISDIR(mode):
                irregular.append(path.relative_to(site).as_posix())
    return files, irregular


def signed_by_a_catalog_key(site: Path) -> bool:
    command = ["openssl", "pkeyutl", "-verify", "-pubin", "-rawin", "-in", str(site / "index.json"), "-sigfile", str(site / "index.json.sig")]
    return any(subprocess.run([*command, "-inkey", str(ROOT / key)], capture_output=True).returncode == 0 for key in KEYS)


def problems(site: Path, floor: int) -> list[str]:
    files, irregular = regular_files(site)
    if irregular:
        return [f"{name} is not a regular file." for name in sorted(irregular)]
    if "index.json" not in files or "index.json.sig" not in files:
        return ["index.json or index.json.sig is missing."]
    if not signed_by_a_catalog_key(site):
        return ["index.json.sig is not a signature of index.json by keys/current.pub or keys/next.pub."]
    index = json.loads(files["index.json"].read_bytes())
    found = []
    if index["version"] <= floor:
        found.append(f"the index has version {index['version']}, but version {floor} is already published.")
    expected = {f"{e['id']}/{e['manifest']['version']}/{f['path']}": f["sha256"] for e in index["extensions"] for f in e["files"]}
    expected |= {f"schema/{p.name}": digest(p.read_bytes()) for p in (ROOT / "schema").glob("*.json")}
    expected |= {"CNAME": digest(CNAME), ".nojekyll": digest(b"")}
    actual = {name: digest(path.read_bytes()) for name, path in files.items() if name not in ("index.json", "index.json.sig")}
    found += [f"{name} is missing." for name in sorted(expected.keys() - actual.keys())]
    found += [f"{name} is not part of the signed index." for name in sorted(actual.keys() - expected.keys())]
    found += [f"{name} differs from its SHA-256 in the index." for name in sorted(expected.keys() & actual.keys()) if expected[name] != actual[name]]
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("site", type=Path)
    parser.add_argument("--floor", type=int, required=True, help="the index version on gh-pages, or 0")
    args = parser.parse_args(argv)
    found = problems(args.site, args.floor)
    for problem in found:
        print(f"verify_site: {problem}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
