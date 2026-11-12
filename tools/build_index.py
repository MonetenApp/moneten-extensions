#!/usr/bin/env python3
"""Build the catalog index and the published package files.

Usage:
  tools/build_index.py --out DIR [--previous INDEX] [--key PEM] [--published TIME]

Writes DIR/index.json and DIR/<id>/<version>/<file> for every package. With
--key, also writes DIR/index.json.sig, the raw Ed25519 signature of the exact
bytes of index.json, made by openssl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

from check_package import irregular_files

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_FILES = ("manifest.json", "README.md", "LICENSE")


class BuildError(Exception):
    pass


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def index_validator() -> jsonschema.Draft202012Validator:
    schemas = {name: json.loads((ROOT / "schema" / name).read_text()) for name in ("index.schema.json", "manifest.schema.json")}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    return jsonschema.Draft202012Validator(schemas["index.schema.json"], registry=registry)


def package_entry(folder: Path, status: dict) -> tuple[dict, dict[str, bytes]]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    contents = {name: (folder / name).read_bytes() for name in sorted({*PUBLISHED_FILES, *manifest["files"]})}
    entry = {
        "id": folder.name,
        "status": status.get(folder.name, {}).get("state", "active"),
        "manifest": manifest,
        "files": [{"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents.items()],
    }
    if folder.name in status:
        entry["note"] = status[folder.name]["note"]
    return entry, contents


def build(out: Path, previous: Path | None, published: str, root: Path = ROOT) -> dict:
    old = json.loads(previous.read_text()) if previous else {"version": 0, "extensions": []}
    status = json.loads((root / "status.json").read_text())
    folders = sorted(p for p in (root / "extensions").iterdir() if p.is_dir())
    missing = sorted({e["id"] for e in old["extensions"]} - {p.name for p in folders})
    if missing:
        raise BuildError(f"published packages have no folder: {', '.join(missing)}. Mark them withdrawn in status.json instead of deleting them.")

    for folder in folders:
        if irregular := irregular_files(folder):
            raise BuildError(f"{', '.join(f'{folder.name}/{name}' for name in irregular)} is not a regular file. Only regular files are published.")

    published_versions = {e["id"]: e["manifest"]["version"] for e in old["extensions"]}
    entries, files = [], {}
    for folder in folders:
        entry, contents = package_entry(folder, status)
        version = entry["manifest"]["version"]
        if entry["id"] in published_versions and version_key(version) < version_key(published_versions[entry["id"]]):
            raise BuildError(f"{entry['id']} has version {version}, but {published_versions[entry['id']]} is already published. A package version never goes back.")
        entries.append(entry)
        for name, data in contents.items():
            path = out / entry["id"] / entry["manifest"]["version"] / name
            if path.exists() and path.read_bytes() != data:
                raise BuildError(f"{path.relative_to(out)} is already published with other content. Raise the version of {entry['id']}.")
            files[path] = data

    index = {"formatVersion": 1, "version": old["version"] + 1, "published": published, "extensions": entries}
    errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in index_validator().iter_errors(index)]
    if errors:
        raise BuildError("the index does not match schema/index.schema.json: " + "; ".join(errors))
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (out / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def sign(out: Path, key: Path) -> None:
    subprocess.run(
        ["openssl", "pkeyutl", "-sign", "-inkey", str(key), "-rawin", "-in", str(out / "index.json"), "-out", str(out / "index.json.sig")],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="the published site folder")
    parser.add_argument("--previous", type=Path, help="the index published before; its version plus 1 is the new version")
    parser.add_argument("--key", type=Path, help="the Ed25519 private key in PEM")
    parser.add_argument("--published", default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    parser.add_argument("--root", type=Path, default=ROOT, help="the catalog repository; default this checkout")
    args = parser.parse_args(argv)
    try:
        index = build(args.out, args.previous, args.published, args.root)
    except BuildError as error:
        print(f"build_index: {error}", file=sys.stderr)
        return 1
    if args.key:
        sign(args.out, args.key)
    print(f"index version {index['version']} with {len(index['extensions'])} package(s) in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
