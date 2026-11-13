import json
import os
import re
import sys
from pathlib import Path

import pytest

from check_package import SchemaValidator, check_package, load_schema
from conftest import ROOT

GUIDE = ROOT / "docs" / "guide"
TUTORIAL = GUIDE / "tutorial"
SKIPPED_FOLDERS = {".git", ".cache", ".venv", "node_modules", "site"}

FENCE = re.compile(r"^[ \t]*(```|~~~)")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
JSON_BLOCK = re.compile(r"^([ \t]*)```json[ \t]*\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
LUA_BLOCK = re.compile(r"^([ \t]*)```lua[ \t]*\n(.*?)^\1```", re.MULTILINE | re.DOTALL)


def markdown_files() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.md") if not SKIPPED_FOLDERS & set(p.relative_to(ROOT).parts[:-1]))


def prose_lines(text: str) -> list[tuple[int, str]]:
    """The lines outside code fences, with inline code removed, so a link in an example is not checked."""
    lines, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append((number, re.sub(r"`[^`]*`", "", line)))
    return lines


def slug(heading: str) -> str:
    """The anchor that GitHub gives a heading."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "").lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    found: dict[str, int] = {}
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (match := HEADING.match(line)):
            base = slug(match[2])
            count = found.get(base, 0)
            found[base] = count + 1
            found[f"{base}-{count}" if count else base] = 1
    return set(found)


def broken_links(path: Path) -> list[str]:
    problems = []
    for number, line in prose_lines(path.read_text(encoding="utf-8")):
        for target in LINK.findall(line):
            if re.match(r"[a-z][a-z0-9+.-]*:", target):
                continue
            file_part, _, anchor = target.partition("#")
            resolved = (path.parent / file_part).resolve() if file_part else path
            where = f"{path.relative_to(ROOT)}:{number}: {target}"
            if not resolved.exists():
                problems.append(f"{where} names a missing file.")
            elif anchor and (resolved.suffix != ".md" or anchor not in anchors(resolved)):
                problems.append(f"{where} names a missing heading.")
    return problems


def manifest_fields() -> set[str]:
    return set(load_schema("manifest.schema.json")["properties"])


def manifest_examples(path: Path) -> list[tuple[int, object]]:
    """Each json block of a page with its line, as parsed JSON, or None when the block is not valid JSON."""
    text = path.read_text(encoding="utf-8")
    examples = []
    for match in JSON_BLOCK.finditer(text):
        try:
            value = json.loads(match[2])
        except json.JSONDecodeError:
            value = None
        examples.append((text.count("\n", 0, match.start()) + 1, value))
    return examples


def is_manifest_part(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value) <= manifest_fields()


def schema_errors(example: dict) -> list[str]:
    """Validates a part of a manifest in place of the same fields of the tutorial manifest."""
    manifest = {**json.loads((TUTORIAL / "manifest.json").read_text()), **example}
    return [error.message for error in SchemaValidator(load_schema("manifest.schema.json")).iter_errors(manifest)]


def property_names(schema: dict) -> set[str]:
    names = set()
    for name, child in schema.get("properties", {}).items():
        names.add(name)
        names |= property_names(child)
        names |= property_names(child.get("items", {}))
    return names


def test_every_relative_link_and_anchor_resolves():
    assert [problem for path in markdown_files() for problem in broken_links(path)] == []


def test_link_check_finds_a_missing_file_and_a_missing_heading(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    (tmp_path / "a.md").write_text("# Start here\n\n[ok](#start-here) [gone](b.md) [bad](a.md#nowhere) `[code](c.md)`\n")
    assert broken_links(tmp_path / "a.md") == [
        "a.md:3: b.md names a missing file.",
        "a.md:3: a.md#nowhere names a missing heading.",
    ]


def test_anchors_follow_github():
    assert {"hosts", "hosts-and-redirects", "manifest-of-a-file-install"} <= anchors(GUIDE / "manifest.md") | anchors(GUIDE / "reference.md")
    assert slug("Step 1: Register the service") == "step-1-register-the-service"
    assert slug("`apiVersion`") == "apiversion"


@pytest.mark.parametrize("page", sorted(GUIDE.glob("*.md")), ids=lambda p: p.name)
def test_every_manifest_example_validates(page):
    failures = []
    for line, value in manifest_examples(page):
        if page.name == "manifest.md" and not is_manifest_part(value):
            failures.append(f"{page.name}:{line}: the block is not a manifest or a part of one.")
        elif is_manifest_part(value) and (errors := schema_errors(value)):
            failures.append(f"{page.name}:{line}: {errors}")
    assert failures == []


def test_manifest_page_has_an_example_for_each_field():
    covered = {key for _, value in manifest_examples(GUIDE / "manifest.md") if is_manifest_part(value) and len(value) == 1 for key in value}
    assert covered == manifest_fields()


def test_manifest_page_names_each_field_of_the_schema():
    text = (GUIDE / "manifest.md").read_text()
    assert sorted(name for name in property_names(load_schema("manifest.schema.json")) if f"`{name}`" not in text) == []


def test_a_wrong_manifest_example_fails():
    assert schema_errors({"hosts": ["*.bank.example"]}) != []
    assert schema_errors({"kinds": ["payments"]}) != []


def test_full_manifests_on_the_pages_are_the_tutorial_manifest():
    package = json.loads((TUTORIAL / "manifest.json").read_text())
    full = [value for page in ("tutorial.md", "manifest.md") for _, value in manifest_examples(GUIDE / page) if is_manifest_part(value) and value.get("id") == "tutorial"]
    assert full == [package, package]


def test_tutorial_package_passes_the_checks(luac):
    assert check_package(TUTORIAL, luac) == []


def lua_blocks(page: Path) -> list[str]:
    return [re.sub(r"^" + match[1], "", match[2], flags=re.MULTILINE) for match in LUA_BLOCK.finditer(page.read_text(encoding="utf-8"))]


def replace_function(script: str, name: str, code: str) -> str:
    old = re.search(rf"^function {name}\(.*?^end\n", script, re.MULTILINE | re.DOTALL)
    assert old, f"{name} is not in the script"
    return script.replace(old[0], code, 1)


def tutorial_script(page: Path) -> str:
    """The script that a reader has after step 2, from the Lua blocks of the tutorial and the edits that the steps name."""
    first, top, initialize, refresh = lua_blocks(page)[:4]
    script = first.replace("}\n\nfunction SupportsBank", "}\n\n" + top + "\nfunction SupportsBank", 1)
    script = replace_function(script, "InitializeSession", initialize)
    return replace_function(script, "RefreshAccount", refresh)


def test_tutorial_steps_compose_to_the_package_script():
    assert tutorial_script(GUIDE / "tutorial.md") == (TUTORIAL / "Tutorial.lua").read_text()


@pytest.mark.skipif(not os.environ.get("EXT"), reason="EXT names no ext binary")
def test_tutorial_recording_replays_with_ext(luac):
    assert check_package(TUTORIAL, luac, ext=os.environ["EXT"]) == []
