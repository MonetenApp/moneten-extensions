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
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
LUA_VERSION = "5.4.8"

SIGN_OFF_LABELS = {"io": "io-acknowledged", "new-host": "hosts-approved"}

FORBIDDEN_GLOBALS = {"load", "loadstring", "dofile", "loadfile", "require", "debug", "package"}
OS_ALLOWED = {"time", "date", "clock", "difftime"}

MAX_LINE = 500
MAX_ESCAPED_BYTES = 200
ENTROPY_MIN_BYTES = 300
ENTROPY_MAX_BITS = 5.5
ENCODED_MAX_CHARS = 300
MIN_LITERAL_ARGUMENTS = 8
MAX_LITERAL_BYTES = 64

ALLOWED_IBAN = "DE02120300000000202051"
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")

LICENSE_TEMPLATES = ROOT / "tools" / "licenses"
RESTRICTING_WORDS = re.compile(r"commercial|commons clause|\bsell|\bsold\b|resale|prohibit|forbid|not permitted|personal use|private use|without (?:the )?(?:prior )?(?:written )?permission|proprietary|\bdo not\b")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str
    warning: bool = False

    @property
    def label(self) -> str | None:
        return SIGN_OFF_LABELS.get(self.rule)

    def render(self, labels: set[str] = frozenset()) -> str:
        text = f"{self.path}:{self.line}: {self.rule}: {self.message}"
        if self.warning or self.label is None:
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


class DuplicateKey(ValueError):
    pass


def unique_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    for key in keys:
        if keys.count(key) > 1:
            raise DuplicateKey(repr(key))
    return dict(pairs)


def check_manifest(pkg: Package) -> tuple[dict | None, list[Finding]]:
    path = pkg.folder / "manifest.json"
    if not path.is_file():
        return None, [Finding(pkg.rel("manifest.json"), 0, "schema", "manifest.json is missing.")]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    except DuplicateKey as error:
        return None, [Finding(pkg.rel("manifest.json"), 0, "schema", f"manifest.json names {error} twice. JSON parsers disagree on which value counts.")]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [Finding(pkg.rel("manifest.json"), getattr(error, "lineno", 0), "schema", f"manifest.json is not valid JSON: {error}")]
    findings = []
    validator = jsonschema.Draft202012Validator(load_schema("manifest.schema.json"))
    for error in sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(part) for part in error.absolute_path) or "(root)"
        findings.append(Finding(pkg.rel("manifest.json"), 1, "schema", f"{where}: {error.message}"))
    if findings:
        return None, findings
    names = [service["name"] for service in manifest["services"]]
    for name in sorted({n for n in names if names.count(n) > 1}):
        findings.append(Finding(pkg.rel("manifest.json"), 1, "schema", f"services: {name!r} appears more than once."))
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


TEMPLATE_PART = re.compile(r'<<(beginOptional|endOptional|var(?:;\w+="(?:[^"\\]|\\.)*")+)>>')


def normalize_license(text: str) -> str:
    """Applies the SPDX matching guidelines that matter here: case, quotes, dashes, the copyright sign, and markup.
    Whitespace becomes single spaces, which compact_license then drops for the comparison."""
    text = text.lower().replace("https:", "http:").replace("(c)", "©")
    text = re.sub(r"[\"“”‘’`´«»„]", "'", text)
    text = re.sub(r"[‐‑‒–—―]+|-+", "-", text)
    return re.sub(r"\s+", " ", re.sub(r"[<>*]", "", text)).strip()


def compact_license(text: str) -> str:
    return normalize_license(text).replace(" ", "")


def license_pattern(spdx_id: str) -> re.Pattern:
    """Compiles an SPDX license template into a regex over compact_license text. Each var becomes a group."""
    template = (LICENSE_TEMPLATES / f"{spdx_id}.template.txt").read_text(encoding="utf-8")
    parts, position, count = [], 0, 0
    for match in TEMPLATE_PART.finditer(template):
        parts.append(re.escape(compact_license(template[position : match.start()])))
        if match[1] == "beginOptional":
            parts.append("(?:")
        elif match[1] == "endOptional":
            parts.append(")?")
        else:
            var = re.search(r'match="((?:[^"\\]|\\.)*)"', match[1])[1].replace("\\s+", "\\s*").replace(" ", "").replace(">", "").replace("<", "").replace(".+", ".{1,300}").replace(".*", ".{0,300}").replace(".{0,5000}", ".{0,1000}")
            var = re.sub(r"\.\{\d+,(\d+)\}", r".{0,\1}", var)
            parts.append(f"(?P<v{count}>{var})")
            count += 1
        position = match.end()
    parts.append(re.escape(compact_license(template[position:])))
    return re.compile("".join(parts), re.IGNORECASE | re.DOTALL)


def check_license(pkg: Package, manifest: dict) -> list[Finding]:
    path = pkg.folder / "LICENSE"
    if not path.is_file():
        return [Finding(pkg.rel("LICENSE"), 0, "license", "LICENSE is missing.")]
    spaced = normalize_license(path.read_text(encoding="utf-8", errors="replace"))
    letters = [i for i, c in enumerate(spaced) if c != " "]
    declared = manifest["license"]
    match = license_pattern(declared).fullmatch(spaced.replace(" ", ""))
    if match is None:
        return [Finding(pkg.rel("LICENSE"), 1, "license", f"LICENSE is not the text of {declared}, the license in manifest.json. Only the names, years, and other blanks of the SPDX template may differ, and nothing may be added.")]
    for group in range(1, len(match.groups()) + 1):
        start, end = match.span(group)
        if end > start and (word := RESTRICTING_WORDS.search(spaced[letters[start] : letters[end - 1] + 1])):
            return [Finding(pkg.rel("LICENSE"), 1, "license", f"LICENSE adds the words {word[0]!r} to the text of {declared}. A catalog package may not restrict its license.")]
    return []


@dataclass
class Instruction:
    line: int
    op: str
    args: list[int]
    comment: str


@dataclass
class LuaFunction:
    first_line: int
    last_line: int
    instructions: list[Instruction] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)
    locals: list[str] = field(default_factory=list)


HEADER = re.compile(r"^(?:main|function) <.*:(\d+),(\d+)>")
INSTRUCTION = re.compile(r"^\t\d+\t\[(\d+)\]\t(\w+)\s*([^;]*?)\s*(?:;\s*(.*))?$")
CONSTANT = re.compile(r'^\t\d+\tS\t"(.*)"$')
LOCAL = re.compile(r"^\t\d+\t(\S+)\t\d+\t\d+$")
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


def quoted_text(comment: str) -> str | None:
    match = re.fullmatch(QUOTED, comment)
    return unescape(match[1]).decode("utf-8", "replace") if match else None


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
    section = "code"
    for row in result.stdout.splitlines():
        if header := HEADER.match(row):
            functions.append(LuaFunction(int(header[1]), int(header[2])))
            section = "code"
        elif row.startswith(("constants (", "locals (", "upvalues (")):
            section = row.split(" ")[0]
        elif section == "constants":
            if constant := CONSTANT.match(row):
                functions[-1].constants.append(constant[1])
        elif section == "locals":
            if local := LOCAL.match(row):
                functions[-1].locals.append(local[1])
        elif section == "code" and (instruction := INSTRUCTION.match(row)):
            args = [int(a) for a in re.findall(r"-?\d+", instruction[3])]
            functions[-1].instructions.append(Instruction(int(instruction[1]), instruction[2], args, instruction[4] or ""))
    for fn in functions:
        fn.instructions = fold_long_global_names(fn.instructions)
    return functions, ""


def fold_long_global_names(instructions: list[Instruction]) -> list[Instruction]:
    """Lua compiles a global with a long name, or one past the 255th constant, as _ENV loaded into a register and indexed.
    This turns each such read or write back into the GETTABUP or SETTABUP that a short name gets."""
    out = list(instructions)
    i = 0
    while i + 1 < len(out):
        env, key = out[i], out[i + 1]
        if env.op == "GETUPVAL" and env.comment == "_ENV" and key.op == "LOADK" and re.fullmatch(QUOTED, key.comment):
            r, k = env.args[0], key.args[0]
            for j in range(i + 2, len(out)):
                use = out[j]
                if use.op == "GETTABLE" and use.args[1:3] == [r, k]:
                    out[j] = Instruction(use.line, "GETTABUP", [use.args[0], 0, 0], f"_ENV {key.comment}")
                elif use.op == "SETTABLE" and use.args[:2] == [r, k]:
                    out[j] = Instruction(use.line, "SETTABUP", [0, 0, use.args[2]], f"_ENV {key.comment}")
                elif not use.args or use.args[0] <= k or use.op in ("SETTABUP", "SETUPVAL", "RETURN", "TAILCALL", "JMP"):
                    break
                else:
                    continue
                del out[i : i + 2]
                break
        i += 1
    return out


def next_field_read(fn: LuaFunction, index: int, register: int) -> str | None:
    if index + 1 >= len(fn.instructions):
        return None
    following = fn.instructions[index + 1]
    if following.op in ("GETFIELD", "SELF") and following.args[1] == register:
        return quoted_text(following.comment)
    return None


def next_is_truth_test(fn: LuaFunction, index: int, register: int) -> bool:
    following = fn.instructions[index + 1] if index + 1 < len(fn.instructions) else None
    return following is not None and following.op == "TEST" and following.args[0] == register


def rawget_key(fn: LuaFunction, index: int, register: int) -> str | None:
    if index == 0 or index + 1 >= len(fn.instructions):
        return None
    before, after = fn.instructions[index - 1], fn.instructions[index + 1]
    if before.op == "GETTABUP" and before.comment == '_ENV "rawget"' and before.args[0] == register - 1:
        if after.op == "LOADK" and after.args[0] == register + 1:
            return quoted_text(after.comment)
    return None


ENV_AS_VALUE = "_ENV is used as a value. The check follows only reads of a fixed global name, such as os.time, so it cannot see what the script reads through it."


def check_globals(rel: str, functions: list[LuaFunction]) -> list[Finding]:
    findings = []
    for fn in functions:
        if "_ENV" in fn.locals:
            findings.append(Finding(rel, fn.first_line, "forbidden", "a local variable or parameter is named _ENV. It replaces the globals of the code after it, so the check cannot see which globals the script reads."))
        for i, ins in enumerate(fn.instructions):
            if ins.op == "GETUPVAL" and ins.comment == "_ENV":
                findings.append(Finding(rel, ins.line, "forbidden", ENV_AS_VALUE))
                continue
            if ins.op == "SELF" and ins.comment == '"dump"':
                findings.append(Finding(rel, ins.line, "forbidden", "string.dump is not available. The check refuses every :dump() call."))
                continue
            if ins.op != "GETTABUP" or not (match := re.fullmatch(r"_ENV " + QUOTED, ins.comment)):
                continue
            name, index, register = unescape(match[1]).decode("utf-8", "replace"), i, ins.args[0]
            if name == "_G":
                if (field_name := next_field_read(fn, index, register)) is not None:
                    name, index, register = field_name, index + 1, fn.instructions[index + 1].args[0]
                elif (key := rawget_key(fn, index, register)) is not None:
                    name, index, register = key, index + 1, -1
                else:
                    findings.append(Finding(rel, ins.line, "forbidden", "_G is used other than as _G.name or rawget(_G, \"name\"). The check cannot see which global the script reads."))
                    continue
            field_name = next_field_read(fn, index, register)
            if name in FORBIDDEN_GLOBALS:
                findings.append(Finding(rel, ins.line, "forbidden", f"{name} is not available."))
            elif name == "os" and field_name is None and not next_is_truth_test(fn, index, register):
                findings.append(Finding(rel, ins.line, "forbidden", "os is used other than as os.time, os.date, os.clock, or os.difftime."))
            elif name == "os" and field_name not in OS_ALLOWED:
                findings.append(Finding(rel, ins.line, "forbidden", f"os.{field_name} is not available."))
            elif name == "string" and field_name == "dump":
                findings.append(Finding(rel, ins.line, "forbidden", "string.dump is not available."))
            elif name == "io":
                what = f"io.{field_name}" if field_name else "io"
                findings.append(Finding(rel, ins.line, "io", f"reads {what}. Moneten gives scripts an io table without functions, so the value is nil."))
    return findings


RUN_TIME = "\0"


@dataclass(eq=False)
class StringValue:
    """A string the script builds from literals. RUN_TIME stands for a piece known only when the script runs."""
    line: int
    text: str
    callee: str | None = None
    argument: int | None = None
    is_piece: bool = False


NO_TARGET_OPS = {
    "SETTABUP", "SETUPVAL", "SETTABLE", "SETI", "SETFIELD", "SETLIST", "JMP", "TEST", "EQ", "LT", "LE", "EQK", "EQI",
    "LTI", "LEI", "GTI", "GEI", "RETURN", "RETURN0", "RETURN1", "CLOSE", "TBC", "EXTRAARG", "MMBIN", "MMBINI", "MMBINK",
    "VARARGPREP", "TFORPREP", "TFORLOOP",
}


def string_values(fn: LuaFunction) -> list[StringValue]:
    """Follows string literals through registers: moves, concatenations, and the call that receives each one."""
    values: dict[int, StringValue] = {}
    names: dict[int, str] = {}
    found: list[StringValue] = []
    loaded: set[str] = set()
    for ins in fn.instructions:
        a = ins.args[0] if ins.args else -1
        if ins.op == "LOADK" and (text := quoted_text(ins.comment)) is not None:
            loaded.add(ins.comment)
            values[a] = StringValue(ins.line, text)
            found.append(values[a])
            names.pop(a, None)
        elif ins.op == "MOVE":
            values.pop(a, None)
            if ins.args[1] in values:
                values[a] = values[ins.args[1]]
        elif ins.op == "CONCAT":
            pieces = [values.get(r) for r in range(a, a + ins.args[1])]
            for piece in pieces:
                if piece is not None:
                    piece.is_piece = True
            joined = StringValue(ins.line, "".join(RUN_TIME if p is None else p.text for p in pieces))
            for r in range(a, a + ins.args[1]):
                values.pop(r, None)
            values[a] = joined
            found.append(joined)
        elif ins.op in ("GETFIELD", "GETTABUP", "SELF"):
            key = re.search(QUOTED + "$", ins.comment)
            names[a] = unescape(key[1]).decode("utf-8", "replace") if key else ""
            receiver = values.get(ins.args[1])
            values.pop(a, None)
            if ins.op == "SELF":
                values.pop(a + 1, None)
                if receiver is not None:
                    values[a + 1] = receiver
        elif ins.op in ("CALL", "TAILCALL"):
            last = a + ins.args[1] - 1 if ins.args[1] > 0 else max(values, default=a)
            for r in range(a + 1, last + 1):
                if r in values and values[r].callee is None:
                    values[r].callee, values[r].argument = names.get(a), r - a
            for r in [r for r in values if r >= a]:
                del values[r]
            for r in [r for r in names if r >= a]:
                del names[r]
        elif ins.op not in NO_TARGET_OPS:
            values.pop(a, None)
            names.pop(a, None)
    lines = constant_lines(fn)
    for printed in fn.constants:
        if f'"{printed}"' not in loaded:
            found.append(StringValue(lines.get(printed, fn.first_line), unescape(printed).decode("utf-8", "replace")))
    return found


def constant_lines(fn: LuaFunction) -> dict[str, int]:
    lines: dict[str, int] = {}
    for ins in fn.instructions:
        for printed in re.findall(QUOTED, ins.comment):
            lines.setdefault(printed, ins.line)
    return lines


URL_START = re.compile(r"([a-z][a-z0-9+.-]*)://|^//", re.IGNORECASE)
AUTHORITY_END = re.compile(r"[/?#\s\"'<>\\\0]")
HOST = re.compile(r"([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])?")
PATTERN_SYNTAX = re.compile(r"^\^|%[^%\w\s]|%[acdglpsuwx][-*+?]|\[\^|\[%|\.[-*+]|[a-z]\?:|[^%]\$$", re.IGNORECASE)
PATTERN_FUNCTIONS = {"find", "match", "gmatch", "gsub"}
ENCODING_FUNCTIONS = {"urlencode"}
UNCONTACTED_HOSTS = {
    "www.w3.org": "is the name of an XML namespace",
    "schemas.xmlsoap.org": "is the name of an XML namespace",
    "service.moneymoney-app.com": "is the OAuth redirect address that the app catches before any request",
}


def is_lua_pattern(value: StringValue) -> bool:
    used_as_pattern = value.callee in PATTERN_FUNCTIONS and value.argument == 2
    return used_as_pattern or PATTERN_SYNTAX.search(value.text) is not None


@dataclass(frozen=True)
class HostProblem:
    message: str
    host_known: bool
    warning_reason: str | None


def host_problems(value: StringValue, hosts: set[str]) -> list[HostProblem]:
    pattern = is_lua_pattern(value)
    text = re.sub(r"%(\W)", r"\1", value.text) if pattern else value.text
    problems = []
    for start in URL_START.finditer(text):
        scheme = (start[1] or "https").lower()
        rest = text[start.end() :]
        end = AUTHORITY_END.search(rest)
        authority = rest[: end.start()] if end else rest
        after = rest[len(authority) : len(authority) + 1]
        host = re.sub(r":\d*$", "", authority.rsplit("@", 1)[-1]).lower()
        host_known = HOST.fullmatch(host) is not None
        if (not start[1] and not host_known) or (not authority and after.isspace()):
            continue
        shown = f"{start[0]}{authority}{'..' if after == RUN_TIME else ''}".replace(RUN_TIME, "..")
        if not host_known:
            if not authority and after in ("", RUN_TIME):
                problem = f"{shown} gets its host when the script runs. Write the host into the string so the check can compare it with the manifest."
            else:
                problem = f"the host of {shown} cannot be determined. Write the host into the string so the check can compare it with the manifest."
        elif scheme == "http":
            problem = f"http://{host} is not HTTPS. Extensions contact hosts only over HTTPS."
        elif scheme != "https":
            problem = f"{scheme}://{host} is not HTTPS. Extensions contact hosts only over HTTPS."
        elif host not in hosts:
            problem = f"{host} is not in the hosts of manifest.json."
        else:
            continue
        before = text[: start.start()]
        if pattern:
            reason = "the string is a Lua pattern, so it matches addresses and is not one"
        elif value.callee in ENCODING_FUNCTIONS:
            reason = f"the string goes into MM.{value.callee}, so it is a value inside a request and not an address the script contacts"
        elif host in UNCONTACTED_HOSTS:
            reason = f"{host} {UNCONTACTED_HOSTS[host]}"
        elif re.search(r"xmlns(:[\w.-]+)?\s*=\s*[\"']$", before):
            reason = "the address is the name of an XML namespace"
        else:
            reason = None
        problems.append(HostProblem(problem, host_known, reason))
    return problems


def check_hosts(rel: str, functions: list[LuaFunction], hosts: set[str]) -> list[Finding]:
    findings = []
    for fn in functions:
        for value in string_values(fn):
            for problem in host_problems(value, hosts):
                if value.is_piece and not problem.host_known:
                    continue
                if problem.warning_reason is None:
                    findings.append(Finding(rel, value.line, "host", problem.message))
                else:
                    findings.append(Finding(rel, value.line, "host", f"{problem.message} Only a warning, because {problem.warning_reason}.", warning=True))
    return list(dict.fromkeys(findings))


def entropy(data: bytes) -> float:
    counts = Counter(data)
    return -sum(n / len(data) * math.log2(n / len(data)) for n in counts.values())


@dataclass
class LuaString:
    line: int
    escaped_bytes: int


def lua_strings(text: str) -> list[LuaString]:
    """Finds the string literals of a Lua source outside comments and counts their numeric escapes."""
    strings = []
    i, line, n = 0, 1, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif text.startswith("--", i):
            long = re.match(r"--\[(=*)\[", text[i:])
            close = text.find(f"]{long[1]}]", i) if long else text.find("\n", i)
            close = n if close < 0 else close
            line += text.count("\n", i, close)
            i = close + (len(long[1]) + 2 if long else 0)
        elif long := re.match(r"\[(=*)\[", text[i : i + 64]):
            close = text.find(f"]{long[1]}]", i)
            close = n if close < 0 else close
            line += text.count("\n", i, close)
            i = close + len(long[1]) + 2
        elif c in "\"'":
            start_line, escaped, i = line, 0, i + 1
            while i < n and text[i] != c:
                if text[i] == "\\" and i + 1 < n:
                    escape = re.match(r"\\(\d{1,3}|x[0-9A-Fa-f]{2}|u\{[0-9A-Fa-f]+\}|z\s*|\r\n|\n|.)", text[i:], re.DOTALL)
                    if escape[1][0].isdigit() or escape[1][0] in "xu":
                        escaped += 1
                    line += escape[0].count("\n")
                    i += len(escape[0])
                else:
                    line += text[i] == "\n"
                    i += 1
            strings.append(LuaString(start_line, escaped))
            i += 1
        else:
            i += 1
    return strings


def innermost(functions: list[LuaFunction], line: int) -> LuaFunction:
    holding = [fn for fn in functions[1:] if fn.first_line <= line <= fn.last_line]
    return min(holding, key=lambda fn: fn.last_line - fn.first_line, default=functions[0])


ENCODED_RUN = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")


def encoded_length(text: str) -> int:
    total = 0
    for run in ENCODED_RUN.finditer(text.replace(RUN_TIME, " ")):
        word = run[0]
        hex_run = re.fullmatch(r"[0-9a-fA-F]+", word) and re.search(r"\d", word) and re.search(r"[a-fA-F]", word)
        base64_run = all(re.search(p, word) for p in (r"[a-z]", r"[A-Z]", r"\d")) and entropy(word.encode()) > 4.0
        if hex_run or base64_run:
            total += len(word)
    return total


def literal_bytes_in_calls(fn: LuaFunction) -> tuple[int, int]:
    """Counts integer literals passed to calls that take at least MIN_LITERAL_ARGUMENTS of them, as string.char does."""
    literal: set[int] = set()
    total, first_line = 0, fn.first_line
    for ins in fn.instructions:
        a = ins.args[0] if ins.args else -1
        if ins.op in ("CALL", "TAILCALL") and ins.args[1] > 0:
            count = sum(r in literal for r in range(a + 1, a + ins.args[1]))
            if count >= MIN_LITERAL_ARGUMENTS:
                first_line = first_line if total else ins.line
                total += count
            literal = {r for r in literal if r < a}
        elif ins.op == "LOADI" and 0 <= ins.args[1] <= 255:
            literal.add(a)
        elif ins.op not in NO_TARGET_OPS:
            literal.discard(a)
    return total, first_line


def check_line_lengths(rel: str, text: str) -> list[Finding]:
    return [
        Finding(rel, number, "obfuscation", f"the line has {len(line)} characters. The limit is {MAX_LINE}.")
        for number, line in enumerate(text.splitlines(), 1)
        if len(line) > MAX_LINE
    ]


def check_obfuscation(rel: str, text: str, functions: list[LuaFunction]) -> list[Finding]:
    findings = []
    escapes: dict[int, list[LuaString]] = {}
    for string in lua_strings(text):
        if string.escaped_bytes:
            escapes.setdefault(id(innermost(functions, string.line)), []).append(string)
    for fn in functions:
        where = "the main chunk" if fn is functions[0] else f"the function on lines {fn.first_line} to {fn.last_line}"
        strings = escapes.get(id(fn), [])
        if (count := sum(s.escaped_bytes for s in strings)) > MAX_ESCAPED_BYTES:
            line = max(strings, key=lambda s: s.escaped_bytes).line
            findings.append(Finding(rel, line, "obfuscation", f"{where} writes {count} bytes as escapes such as \\104 or \\x68. The limit is {MAX_ESCAPED_BYTES} per function."))
        count, line = literal_bytes_in_calls(fn)
        if count > MAX_LITERAL_BYTES:
            findings.append(Finding(rel, line, "obfuscation", f"{where} passes {count} bytes as numbers to calls such as string.char. The limit is {MAX_LITERAL_BYTES} per function."))
        values = [value for value in string_values(fn) if not value.is_piece]
        if not values:
            continue
        line = max(values, key=lambda v: len(v.text)).line
        data = "".join(value.text for value in values).replace(RUN_TIME, "")
        if (count := sum(encoded_length(value.text) for value in values)) > ENCODED_MAX_CHARS:
            findings.append(Finding(rel, line, "obfuscation", f"{where} holds {count} characters of hex or base64 in its strings. The limit is {ENCODED_MAX_CHARS} per function."))
        raw = data.encode("utf-8", "replace")
        if len(raw) > ENTROPY_MIN_BYTES and (bits := entropy(raw)) > ENTROPY_MAX_BITS:
            findings.append(Finding(rel, line, "obfuscation", f"the strings of {where} hold {len(raw)} bytes with {bits:.2f} bits per byte, which looks encoded or encrypted. The limit is {ENTROPY_MAX_BITS} above {ENTROPY_MIN_BYTES} bytes per function."))
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
        findings += check_line_lengths(rel, text)
        functions, error = compile_listing(luac, path)
        if functions is None:
            findings.append(Finding(rel, int(m[1]) if (m := re.search(r":(\d+):", error)) else 0, "syntax", error))
            continue
        findings += check_obfuscation(rel, text, functions)
        findings += check_globals(rel, functions)
        findings += check_hosts(rel, functions, set(manifest["hosts"]))
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
        failing = [f for f in findings if not f.label and not f.warning]
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    for finding in shown:
        print(finding.render(labels))
        if github:
            level = "error" if finding in failing else "notice" if finding.label in labels else "warning"
            print(f"::{level} file={finding.path},line={max(finding.line, 1)},title={finding.rule}::{finding.render(labels)}")

    sys.stdout.flush()
    skipped = "" if args.ext else " ext test skipped, no ext binary."
    print(f"Checked {len(folders)} package(s): {len(failing)} failing, {len(shown) - len(failing)} other.{skipped}", file=sys.stderr)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
