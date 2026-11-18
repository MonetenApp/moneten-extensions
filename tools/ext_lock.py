#!/usr/bin/env python3
"""Read tools/ext.lock and print its fields as name=value lines for $GITHUB_OUTPUT.

Usage:
  tools/ext_lock.py [LOCK]

The lock pins a signed release of ext from MonetenApp/Moneten. It holds the four fields version,
commit, url, and sha256, each one time. All four empty skip the job ext test. Otherwise each field
must be valid: a version of the form 1.2.3, a full commit, the URL of the zip of the release
ext-v<version>, and a SHA-256. A wrong field fails the job checks, so a typo never skips ext test.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LOCK = Path(__file__).resolve().parent / "ext.lock"
FIELDS = ("version", "commit", "url", "sha256")
RELEASES = "https://github.com/MonetenApp/Moneten/releases/download"


class LockError(Exception):
    pass


def release_url(version: str) -> str:
    """The only URL that the release ext-v<version> gives its zip."""
    return f"{RELEASES}/ext-v{version}/ext-{version}-macos.zip"


def parse(text: str) -> dict[str, str]:
    """The fields of the lock. Raises LockError for a missing, repeated, unknown, or malformed field."""
    found: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name not in FIELDS:
            raise LockError(f"line {number} is not one of {', '.join(f + '=' for f in FIELDS)}.")
        if name in found:
            raise LockError(f"line {number} repeats {name}.")
        found[name] = value
    missing = [name for name in FIELDS if name not in found]
    if missing:
        raise LockError(f"{', '.join(missing)} is missing.")
    if not any(found.values()):
        return found
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", found["version"]):
        raise LockError("version must be of the form 1.2.3.")
    if not re.fullmatch(r"[0-9a-f]{40}", found["commit"]):
        raise LockError("commit must be a full commit of MonetenApp/Moneten in lowercase hex.")
    if found["url"] != release_url(found["version"]):
        raise LockError(f"url must be {release_url(found['version'])}.")
    if not re.fullmatch(r"[0-9a-f]{64}", found["sha256"]):
        raise LockError("sha256 must be 64 lowercase hex digits.")
    return found


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else LOCK
    try:
        fields = parse(path.read_text(encoding="utf-8"))
    except LockError as error:
        print(f"::error file=tools/ext.lock::{error}", file=sys.stderr)
        return 1
    for name in FIELDS:
        print(f"{name}={fields[name]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
