#!/usr/bin/env python3
"""Check catalog packages. Prints one line per finding as path:line: rule: message.

Usage:
  tools/check_package.py [PACKAGE ...] [--base REF [--changed]] [--sign-off --labels L1,L2] [--ext PATH]

Without PACKAGE, it checks every folder in extensions/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
LUA_VERSION = "5.4.8"

SIGN_OFF_LABELS = {"io": "io-acknowledged", "new-host": "hosts-approved"}

FORBIDDEN_GLOBALS = {"load", "loadstring", "dofile", "loadfile", "require", "debug", "package"}
OS_ALLOWED = {"time", "date", "clock", "difftime"}
UNCONTACTED_HOSTS = {"service.moneymoney-app.com", "www.w3.org", "schemas.xmlsoap.org"}

MAX_LINE = 500
MAX_ESCAPED_BYTES = 200
ENTROPY_MIN_BYTES = 300
ENTROPY_MAX_BITS = 5.5

ALLOWED_IBAN = "DE02120300000000202051"
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")

LICENSE_PHRASES = {
    "MIT": ["permission is hereby granted, free of charge, to any person obtaining a copy"],
    "BSD-2-Clause": ["redistribution and use in source and binary forms"],
    "BSD-3-Clause": ["redistribution and use in source and binary forms", "neither the name"],
    "ISC": ["permission to use, copy, modify, and/or distribute this software for any purpose"],
    "Apache-2.0": ["apache license", "version 2.0, january 2004"],
    "MPL-2.0": ["mozilla public license version 2.0"],
    "LGPL-2.1-or-later": ["gnu lesser general public license version 2.1, february 1999"],
    "LGPL-3.0-or-later": ["gnu lesser general public license version 3, 29 june 2007"],
    "GPL-3.0-or-later": ["gnu general public license version 3, 29 june 2007"],
}
LICENSE_EXCLUDED_PHRASES = {"BSD-2-Clause": ["neither the name"]}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    @property
    def label(self) -> str | None:
        return SIGN_OFF_LABELS.get(self.rule)

    def render(self, labels: set[str] = frozenset()) -> str:
        text = f"{self.path}:{self.line}: {self.rule}: {self.message}"
        if self.label is None:
            return text
        if self.label in labels:
            return f"{text} Acknowledged by the label {self.label}."
        return f"{text} Needs the label {self.label} from a maintainer."


class Package:
    def __init__(self, folder: Path):
        self.folder = folder.resolve()
        self.id = self.folder.name
        self.root = self.folder.parent.parent

    def rel(self, name: str) -> str:
        return f"extensions/{self.id}/{name}"


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "schema" / name).read_text())


def check_manifest(pkg: Package) -> tuple[dict | None, list[Finding]]:
    path = pkg.folder / "manifest.json"
    if not path.is_file():
        return None, [Finding(pkg.rel("manifest.json"), 0, "schema", "manifest.json is missing.")]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [Finding(pkg.rel("manifest.json"), getattr(error, "lineno", 0), "schema", f"manifest.json is not valid JSON: {error}")]
    findings = []
    validator = jsonschema.Draft202012Validator(load_schema("manifest.schema.json"))
    for error in sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(part) for part in error.absolute_path) or "(root)"
        findings.append(Finding(pkg.rel("manifest.json"), 1, "schema", f"{where}: {error.message}"))
    if findings:
        return None, findings
    if manifest["id"] != pkg.id:
        findings.append(Finding(pkg.rel("manifest.json"), 1, "schema", f"id is {manifest['id']!r} but the folder is {pkg.id!r}."))
    return manifest, findings


def check_layout(pkg: Package, manifest: dict) -> list[Finding]:
    expected = {"manifest.json", "README.md", "LICENSE", "recording/fixture.json", "recording/expected.json", *manifest["files"]}
    present = {p.relative_to(pkg.folder).as_posix() for p in pkg.folder.rglob("*") if p.is_file()}
    findings = [Finding(pkg.rel(name), 0, "layout", f"{name} is missing.") for name in sorted(expected - present) if name != "LICENSE"]
    findings += [
        Finding(pkg.rel(name), 0, "layout", "This file is not part of a package. A package holds manifest.json, README.md, LICENSE, the Lua files in manifest files, and recording/.")
        for name in sorted(present - expected)
    ]
    for name in ("recording/fixture.json", "recording/expected.json"):
        if name in present:
            try:
                json.loads((pkg.folder / name).read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                findings.append(Finding(pkg.rel(name), getattr(error, "lineno", 0), "layout", f"not valid JSON: {error}"))
    return findings


def check_license(pkg: Package, manifest: dict) -> list[Finding]:
    path = pkg.folder / "LICENSE"
    if not path.is_file():
        return [Finding(pkg.rel("LICENSE"), 0, "license", "LICENSE is missing.")]
    text = " ".join(path.read_text(encoding="utf-8", errors="replace").lower().split())
    declared = manifest["license"]
    found = all(p in text for p in LICENSE_PHRASES[declared]) and not any(p in text for p in LICENSE_EXCLUDED_PHRASES.get(declared, []))
    if found:
        return []
    return [Finding(pkg.rel("LICENSE"), 1, "license", f"LICENSE does not hold the text of {declared}, the license in manifest.json.")]


@dataclass
class Instruction:
    line: int
    op: str
    args: list[int]
    comment: str


@dataclass
class LuaFunction:
    line: int
    instructions: list[Instruction]
    constants: list[str]


HEADER = re.compile(r"^(?:main|function) <.*:(\d+),\d+>")
INSTRUCTION = re.compile(r"^\t\d+\t\[(\d+)\]\t(\w+)\s*([^;]*?)\s*(?:;\s*(.*))?$")
CONSTANT = re.compile(r'^\t\d+\tS\t"(.*)"$')
QUOTED = r'"((?:[^"\\]|\\.)*)"'
ESCAPES = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11, '"': 34, "\\": 92}


def unescape(printed: str) -> bytes:
    out = bytearray()
    i = 0
    while i < len(printed):
        c = printed[i]
        if c != "\\":
            out += c.encode("utf-8")
            i += 1
        elif printed[i + 1] in ESCAPES:
            out.append(ESCAPES[printed[i + 1]])
            i += 2
        else:
            digits = re.match(r"\d{1,3}", printed[i + 1 :])[0]
            out.append(int(digits))
            i += 1 + len(digits)
    return bytes(out)


def luac_path() -> str:
    luac = os.environ.get("LUAC") or str(ROOT / ".cache" / f"lua-{LUA_VERSION}" / "src" / "luac")
    try:
        version = subprocess.run([luac, "-v"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        sys.exit(f"luac not found at {luac}. Run tools/setup.sh or set LUAC.")
    if not version.startswith(f"Lua {LUA_VERSION} "):
        sys.exit(f"{luac} is not Lua {LUA_VERSION}: {version.strip()}")
    return luac


def compile_listing(luac: str, path: Path) -> tuple[list[LuaFunction] | None, str]:
    result = subprocess.run([luac, "-p", "-l", "-l", str(path)], capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        return None, result.stderr.strip()
    functions: list[LuaFunction] = []
    in_constants = False
    for row in result.stdout.splitlines():
        if header := HEADER.match(row):
            functions.append(LuaFunction(int(header[1]), [], []))
            in_constants = False
        elif row.startswith("constants ("):
            in_constants = True
        elif row.startswith(("locals (", "upvalues (")):
            in_constants = False
        elif in_constants:
            if constant := CONSTANT.match(row):
                functions[-1].constants.append(constant[1])
        elif instruction := INSTRUCTION.match(row):
            args = [int(a) for a in re.findall(r"-?\d+", instruction[3])]
            functions[-1].instructions.append(Instruction(int(instruction[1]), instruction[2], args, instruction[4] or ""))
    return functions, ""


def next_field_read(fn: LuaFunction, index: int, register: int) -> str | None:
    if index + 1 >= len(fn.instructions):
        return None
    following = fn.instructions[index + 1]
    if following.op in ("GETFIELD", "SELF") and following.args[1] == register:
        match = re.fullmatch(QUOTED, following.comment)
        return unescape(match[1]).decode("utf-8", "replace") if match else None
    return None


def next_is_truth_test(fn: LuaFunction, index: int, register: int) -> bool:
    following = fn.instructions[index + 1] if index + 1 < len(fn.instructions) else None
    return following is not None and following.op == "TEST" and following.args[0] == register


def rawget_key(fn: LuaFunction, index: int, register: int) -> str | None:
    if index == 0 or index + 1 >= len(fn.instructions):
        return None
    before, after = fn.instructions[index - 1], fn.instructions[index + 1]
    if before.op == "GETTABUP" and before.comment == '_ENV "rawget"' and before.args[0] == register - 1:
        if after.op == "LOADK" and after.args[0] == register + 1 and (match := re.fullmatch(QUOTED, after.comment)):
            return unescape(match[1]).decode("utf-8", "replace")
    return None


def check_globals(rel: str, functions: list[LuaFunction]) -> list[Finding]:
    findings = []
    for fn in functions:
        for i, ins in enumerate(fn.instructions):
            if ins.op == "SELF" and ins.comment == '"dump"':
                findings.append(Finding(rel, ins.line, "forbidden", "string.dump is not available. The check refuses every :dump() call."))
                continue
            if ins.op != "GETTABUP" or not (match := re.fullmatch(r"_ENV " + QUOTED, ins.comment)):
                continue
            name, index, register = unescape(match[1]).decode("utf-8", "replace"), i, ins.args[0]
            if name == "_G":
                if (field := next_field_read(fn, index, register)) is not None:
                    name, index, register = field, index + 1, fn.instructions[index + 1].args[0]
                elif (key := rawget_key(fn, index, register)) is not None:
                    name, index, register = key, index + 1, -1
                else:
                    findings.append(Finding(rel, ins.line, "forbidden", "_G is used other than as _G.name or rawget(_G, \"name\"). The check cannot see which global the script reads."))
                    continue
            field = next_field_read(fn, index, register)
            if name in FORBIDDEN_GLOBALS:
                findings.append(Finding(rel, ins.line, "forbidden", f"{name} is not available."))
            elif name == "os" and field is None and not next_is_truth_test(fn, index, register):
                findings.append(Finding(rel, ins.line, "forbidden", "os is used other than as os.time, os.date, os.clock, or os.difftime."))
            elif name == "os" and field not in OS_ALLOWED:
                findings.append(Finding(rel, ins.line, "forbidden", f"os.{field} is not available."))
            elif name == "string" and field == "dump":
                findings.append(Finding(rel, ins.line, "forbidden", "string.dump is not available."))
            elif name == "io":
                what = f"io.{field}" if field else "io"
                findings.append(Finding(rel, ins.line, "io", f"reads {what}. Moneten gives scripts an io table without functions, so the value is nil."))
    return findings


def constant_lines(fn: LuaFunction) -> dict[str, int]:
    lines: dict[str, int] = {}
    for ins in fn.instructions:
        for printed in re.findall(QUOTED, ins.comment):
            lines.setdefault(printed, ins.line)
    return lines


URL = re.compile(rb"(https?)://([^/\s\"'?#:<>\\]*)", re.IGNORECASE)


def check_constants(rel: str, functions: list[LuaFunction], hosts: set[str]) -> list[Finding]:
    findings = []
    for fn in functions:
        lines = constant_lines(fn)
        for printed in fn.constants:
            line = lines.get(printed, fn.line)
            value = unescape(printed)
            for url in URL.finditer(value):
                scheme, host = url[1].lower(), url[2].decode("utf-8", "replace").lower()
                if not host and url.end() == len(value):
                    findings.append(Finding(rel, line, "host", "a string ends in :// and the host is added at run time. Write the host into the string so the check can compare it with the manifest."))
                elif is_lua_pattern(host) or host in UNCONTACTED_HOSTS:
                    continue
                elif scheme == b"http":
                    findings.append(Finding(rel, line, "host", f"http://{host} is not HTTPS. Extensions contact hosts only over HTTPS."))
                elif host not in hosts:
                    findings.append(Finding(rel, line, "host", f"{host} is not in the hosts of manifest.json."))
            if len(value) > ENTROPY_MIN_BYTES and entropy(value) > ENTROPY_MAX_BITS:
                findings.append(Finding(rel, line, "obfuscation", f"a string of {len(value)} bytes with {entropy(value):.2f} bits per byte looks encoded or encrypted. The limit is {ENTROPY_MAX_BITS} above {ENTROPY_MIN_BYTES} bytes."))
    return findings


def is_lua_pattern(host: str) -> bool:
    return re.fullmatch(r"[a-z0-9.-]+", host) is None


def entropy(data: bytes) -> float:
    counts = Counter(data)
    return -sum(n / len(data) * math.log2(n / len(data)) for n in counts.values())


ESCAPED_RUN = re.compile(r"(?:\\(?:x[0-9A-Fa-f]{2}|\d{1,3}))+")


def check_source_text(rel: str, text: str) -> list[Finding]:
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > MAX_LINE:
            findings.append(Finding(rel, number, "obfuscation", f"the line has {len(line)} characters. The limit is {MAX_LINE}."))
        for run in ESCAPED_RUN.finditer(line):
            count = len(re.findall(r"\\(?:x[0-9A-Fa-f]{2}|\d{1,3})", run[0]))
            if count > MAX_ESCAPED_BYTES:
                findings.append(Finding(rel, number, "obfuscation", f"a string of {count} escaped bytes. The limit is {MAX_ESCAPED_BYTES}."))
    return findings


def check_lua(pkg: Package, manifest: dict, luac: str) -> list[Finding]:
    findings = []
    for name in manifest["files"]:
        path = pkg.folder / name
        if not path.is_file():
            continue
        rel = pkg.rel(name)
        data = path.read_bytes()
        if data.startswith(b"\x1bLua"):
            findings.append(Finding(rel, 1, "obfuscation", "the file is compiled Lua bytecode. Catalog packages hold source code."))
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            findings.append(Finding(rel, data[: error.start].count(b"\n") + 1, "obfuscation", "the file is not UTF-8 text."))
            continue
        findings += check_source_text(rel, text)
        functions, error = compile_listing(luac, path)
        if functions is None:
            findings.append(Finding(rel, int(m[1]) if (m := re.search(r":(\d+):", error)) else 0, "syntax", error))
            continue
        findings += check_globals(rel, functions)
        findings += check_constants(rel, functions, set(manifest["hosts"]))
    return findings


IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


def valid_iban(candidate: str) -> bool:
    digits = "".join(str(int(c, 36)) for c in candidate[4:] + candidate[:4])
    return 15 <= len(candidate) <= 34 and int(digits) % 97 == 1


def check_recording(pkg: Package) -> list[Finding]:
    findings = []
    for name in ("recording/fixture.json", "recording/expected.json"):
        path = pkg.folder / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for match in IBAN.finditer(line):
                iban = match[0].replace(" ", "")
                if iban != ALLOWED_IBAN and valid_iban(iban):
                    findings.append(Finding(pkg.rel(name), number, "personal-data", f"the IBAN {iban} looks real. Use the sample IBAN {ALLOWED_IBAN}."))
            for match in EMAIL.finditer(line):
                domain = match[1].lower()
                if not any(domain == d or domain.endswith("." + d) for d in ALLOWED_EMAIL_DOMAINS):
                    findings.append(Finding(pkg.rel(name), number, "personal-data", f"the email address {match[0]} is not on example.com, example.org, or example.net."))
    return findings


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def base_manifest(root: Path, base: str, package_id: str) -> dict | None:
    result = git(root, "show", f"{base}:extensions/{package_id}/manifest.json")
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def check_against_base(pkg: Package, manifest: dict, base: str) -> list[Finding]:
    old = base_manifest(pkg.root, base, pkg.id)
    old_hosts = set(old["hosts"]) if old and isinstance(old.get("hosts"), list) else set()
    manifest_lines = (pkg.folder / "manifest.json").read_text().splitlines()
    findings = []
    for host in manifest["hosts"]:
        if host not in old_hosts:
            line = next((n for n, text in enumerate(manifest_lines, 1) if f'"{host}"' in text), 1)
            findings.append(Finding(pkg.rel("manifest.json"), line, "new-host", f"adds the host {host}."))
    if old and isinstance(old.get("version"), str) and re.fullmatch(r"[0-9]+(\.[0-9]+)*", old["version"]):
        changed = git(pkg.root, "diff", "--quiet", base, "--", f"extensions/{pkg.id}", f":(exclude)extensions/{pkg.id}/recording").returncode != 0
        if changed and version_key(manifest["version"]) <= version_key(old["version"]):
            findings.append(Finding(pkg.rel("manifest.json"), 1, "version", f"the package changed, so its version must be higher than {old['version']}."))
    return findings


def removed_packages(root: Path, base: str) -> list[Finding]:
    listed = git(root, "ls-tree", "--name-only", f"{base}:extensions").stdout.split()
    return [
        Finding(f"extensions/{package_id}", 0, "removed", "the package was deleted. Mark it withdrawn in status.json instead, so installed copies stop.")
        for package_id in listed
        if not (root / "extensions" / package_id).is_dir()
    ]


def changed_package_ids(root: Path, base: str) -> list[str]:
    names = git(root, "diff", "--name-only", base, "--", "extensions").stdout.split()
    return sorted({name.split("/")[1] for name in names if name.count("/") >= 2})


def check_status(root: Path) -> list[Finding]:
    status = json.loads((root / "status.json").read_text())
    validator = jsonschema.Draft202012Validator(load_schema("status.schema.json"))
    findings = [Finding("status.json", 1, "schema", error.message) for error in validator.iter_errors(status)]
    if isinstance(status, dict):
        findings += [Finding("status.json", 1, "schema", f"{package_id} has no folder in extensions/.") for package_id in status if not (root / "extensions" / package_id).is_dir()]
    return findings


def check_ext_test(pkg: Package, ext: str) -> list[Finding]:
    recording = pkg.folder / "recording"
    command = [ext, "test", str(pkg.folder), str(recording / "fixture.json"), str(recording / "expected.json")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        return []
    output = " | ".join((result.stdout + result.stderr).strip().splitlines()[:5])
    return [Finding(pkg.rel("recording/expected.json"), 0, "ext-test", f"ext test exited with {result.returncode}: {output}")]


def check_package(folder: Path, luac: str, base: str | None = None, ext: str | None = None) -> list[Finding]:
    pkg = Package(folder)
    manifest, findings = check_manifest(pkg)
    if manifest is None:
        return findings
    findings += check_layout(pkg, manifest)
    findings += check_license(pkg, manifest)
    findings += check_lua(pkg, manifest, luac)
    findings += check_recording(pkg)
    if base:
        findings += check_against_base(pkg, manifest, base)
    if ext:
        findings += check_ext_test(pkg, ext)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("packages", nargs="*", type=Path, help="package folders; default every folder in extensions/")
    parser.add_argument("--base", help="git ref to compare with, for new hosts, version bumps, and deleted packages")
    parser.add_argument("--changed", action="store_true", help="check only the packages that changed since --base")
    parser.add_argument("--sign-off", action="store_true", help="report only findings that need a maintainer label, and fail on a missing label")
    parser.add_argument("--labels", default="", help="comma-separated labels of the pull request")
    parser.add_argument("--ext", help="path to the ext binary; runs ext test on each recording")
    parser.add_argument("--root", type=Path, default=ROOT, help="the catalog repository; default this checkout")
    args = parser.parse_args(argv)
    if args.changed and not args.base:
        parser.error("--changed needs --base")

    if args.packages:
        folders = args.packages
    elif args.changed:
        folders = [args.root / "extensions" / i for i in changed_package_ids(args.root, args.base) if (args.root / "extensions" / i).is_dir()]
    else:
        folders = sorted(p for p in (args.root / "extensions").iterdir() if p.is_dir())

    luac = luac_path()
    findings: list[Finding] = []
    for folder in folders:
        findings += check_package(folder, luac, args.base, args.ext)
    if not args.packages and not args.changed:
        findings += check_status(args.root)
        if args.base:
            findings += removed_packages(args.root, args.base)

    labels = {label.strip() for label in args.labels.split(",") if label.strip()}
    if args.sign_off:
        shown = [f for f in findings if f.label]
        failing = [f for f in shown if f.label not in labels]
    else:
        shown = findings
        failing = [f for f in findings if not f.label]
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    for finding in shown:
        print(finding.render(labels))
        if github:
            level = "error" if finding in failing else "warning"
            print(f"::{level} file={finding.path},line={max(finding.line, 1)},title={finding.rule}::{finding.render(labels)}")

    skipped = "" if args.ext else " ext test skipped, no ext binary."
    print(f"Checked {len(folders)} package(s): {len(failing)} failing, {len(shown) - len(failing)} other.{skipped}", file=sys.stderr)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
