import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import check_package
from conftest import git
from check_package import check_package as check

TOOLS = Path(__file__).resolve().parent.parent
LUA = "extensions/example/Example.lua"
MANIFEST = "extensions/example/manifest.json"
FIXTURE = "extensions/example/recording/fixture.json"


def package(catalog):
    return catalog / "extensions" / "example"


def append_lua(catalog, code):
    script = package(catalog) / "Example.lua"
    lines = script.read_text().splitlines()
    script.write_text("\n".join([*lines, *code.splitlines()]) + "\n")
    return len(lines) + 1


def edit_manifest(catalog, **changes):
    path = package(catalog) / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(changes)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def summary(findings):
    return [(f.path, f.line, f.rule) for f in findings]


def test_example_package_passes(catalog, luac):
    assert check(package(catalog), luac) == []


def test_os_execute_fails_with_file_and_line(catalog, luac):
    line = append_lua(catalog, 'os.execute("ls")')
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "forbidden")]
    assert findings[0].message == "os.execute is not available."


def test_require_fails(catalog, luac):
    line = append_lua(catalog, 'local x = require("x")')
    assert summary(check(package(catalog), luac)) == [(LUA, line, "forbidden")]


def test_forbidden_global_through_g_fails(catalog, luac):
    line = append_lua(catalog, 'local f = _G.load\nlocal g = rawget(_G, "dofile")\nlocal h = _G[f]')
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "forbidden"), (LUA, line + 1, "forbidden"), (LUA, line + 2, "forbidden")]
    assert [f.message.split(" ")[0] for f in findings] == ["load", "dofile", "_G"]


def test_string_dump_fails(catalog, luac):
    line = append_lua(catalog, 'local a = string.dump\nlocal b = ("x"):dump()')
    assert summary(check(package(catalog), luac)) == [(LUA, line, "forbidden"), (LUA, line + 1, "forbidden")]


@pytest.mark.parametrize("code", [
    "local s = string\nlocal n = 1\nlocal d = s.dump",
    "local d = (function() return string end)().dump",
    'local d = getmetatable("").__index.dump',
])
def test_string_dump_through_another_name_fails(catalog, luac, code):
    line = append_lua(catalog, code) + code.count("\n")
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "forbidden")]
    assert "dump" in findings[0].message


def test_rawget_of_g_with_a_computed_key_fails(catalog, luac):
    line = append_lua(catalog, 'local f = rawget(_G, "lo" .. "ad")')
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "forbidden")]
    assert findings[0].message.startswith("_G is used other than")


def test_io_open_guard_needs_a_label_and_is_no_error(catalog, luac):
    line = append_lua(catalog, "if io ~= nil and io.open ~= nil then\n  local f = io.open(\"x\")\nend")
    findings = check(package(catalog), luac)
    assert {(f.line, f.rule, f.label) for f in findings} == {(line, "io", "io-acknowledged"), (line + 1, "io", "io-acknowledged")}


def test_unlisted_host_fails(catalog, luac):
    line = append_lua(catalog, 'local pixel = "https://tracker.example/p"')
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "host")]
    assert findings[0].message == "tracker.example is not in the hosts of manifest.json."


def test_plain_http_and_host_built_at_run_time_fail(catalog, luac):
    line = append_lua(catalog, 'local a = "http://www.bank.example/"\nlocal b = "https://" .. tostring(a)')
    assert summary(check(package(catalog), luac)) == [(LUA, line, "host"), (LUA, line + 1, "host")]


@pytest.mark.parametrize("code", [
    'local e = _ENV; e.os.execute("ls")',
    'local k = "lo" .. "ad"; _ENV[k]("x")',
    'for name, value in pairs(_ENV) do end',
    'local t = setmetatable({}, {__index = _ENV})',
])
def test_env_used_as_a_value_fails(catalog, luac, code):
    line = append_lua(catalog, code)
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "forbidden")]
    assert findings[0].message.startswith("_ENV is used as a value.")


def test_parameter_named_env_fails(catalog, luac):
    line = append_lua(catalog, "local function f(_ENV) return load end")
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "forbidden")]
    assert findings[0].message.startswith("a local variable or parameter is named _ENV.")


def test_global_with_a_long_name_is_a_fixed_global_read(catalog, luac):
    append_lua(catalog, "ThisGlobalNameIsLongerThanFortyCharactersInTotal = function() end\nThisGlobalNameIsLongerThanFortyCharactersInTotal()")
    assert check(package(catalog), luac) == []


@pytest.mark.parametrize("code, message", [
    ('local u = string.format("https://%s/p", "tracker.example")', "the host of https://%s cannot be determined."),
    ('local u = "https:/" .. "/" .. "tracker.example" .. "/p"', "tracker.example is not in the hosts of manifest.json."),
    ('local h = "tracker.example"\nlocal u = "https://" .. h', "tracker.example is not in the hosts of manifest.json."),
    ('local u = "https://www.bank.example@tracker.example/p"', "tracker.example is not in the hosts of manifest.json."),
    ('local u = "https://user@tracker.example:443/p"', "tracker.example is not in the hosts of manifest.json."),
    ('local u = "https://{h}/p"', "the host of https://{h} cannot be determined."),
    ('local u = "//tracker.example/p"', "tracker.example is not in the hosts of manifest.json."),
    ('local u = "https://" .. string.reverse("elpmaxe.rekcart")', "https://.. gets its host when the script runs."),
    ('local s = "https://tracker.example/p"\nlocal t = "^" .. s', "tracker.example is not in the hosts of manifest.json."),
    ('local u = "https://tracker.example/p$"', "tracker.example is not in the hosts of manifest.json."),
    ('local u = "https://tracker.example/a.*"', "tracker.example is not in the hosts of manifest.json."),
    ('local u = "https://tracker.example/?s?:"', "tracker.example is not in the hosts of manifest.json."),    ('local u = string.char(104,116,116,112,115,58,47) .. string.char(47,116,114,97,99,107,101) .. string.char(114,46,101,120,97,109,112) .. string.char(108,101)', "tracker.example is not in the hosts of manifest.json."),
])
def test_host_hidden_from_a_plain_literal_fails(catalog, luac, code, message):
    append_lua(catalog, code)
    findings = [f for f in check(package(catalog), luac) if not f.warning]
    assert [f.rule for f in findings] == ["host"]
    assert findings[0].message.startswith(message)


def test_declared_host_built_from_pieces_passes(catalog, luac):
    append_lua(catalog, 'local u = "https://" .. "www.bank.example" .. "/login"')
    assert check(package(catalog), luac) == []


def test_patterns_and_addresses_that_are_never_contacted_only_warn(catalog):
    line = append_lua(catalog, "\n".join([
        'local a = ("x"):match("^https://")',
        'local b = "^https://([^/]+)"',
        'local c = MM.urlencode("http://specs.openid.net/auth/2.0")',
        'local d = \'<e xmlns="http://www.ebs.ie/schema"/>\'',
        'local e = "www%.bank%.example"',
        'local f = ("x"):match("^https://www%.bank%.example/")',
    ]))
    result = run_cli(catalog)
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert [text.split(": ")[0] for text in lines] == [f"{LUA}:{line + n}" for n in range(4)]
    assert all("Only a warning, because " in text for text in lines)
    assert "the string is a Lua pattern" in lines[0]
    assert "MM.urlencode" in lines[2]
    assert "XML namespace" in lines[3]


def test_missing_license_fails(catalog, luac):
    (package(catalog) / "LICENSE").unlink()
    assert summary(check(package(catalog), luac)) == [("extensions/example/LICENSE", 0, "license")]


def test_license_outside_the_allowlist_fails(catalog, luac):
    edit_manifest(catalog, license="CC-BY-NC-4.0")
    findings = check(package(catalog), luac)
    assert summary(findings) == [(MANIFEST, 1, "schema")]
    assert findings[0].message.startswith("license: 'CC-BY-NC-4.0' is not one of")


def test_license_text_that_does_not_match_the_manifest_fails(catalog, luac):
    edit_manifest(catalog, license="GPL-3.0-or-later")
    assert summary(check(package(catalog), luac)) == [("extensions/example/LICENSE", 1, "license")]


@pytest.mark.parametrize("spdx_id", sorted(p.stem for p in (TOOLS / "tests" / "licenses").glob("*.txt")))
def test_full_text_of_each_allowed_license_passes(catalog, luac, spdx_id):
    shutil.copy(TOOLS / "tests" / "licenses" / f"{spdx_id}.txt", package(catalog) / "LICENSE")
    edit_manifest(catalog, license=spdx_id)
    assert check(package(catalog), luac) == []


def test_mit_with_a_commons_clause_fails(catalog, luac):
    license = package(catalog) / "LICENSE"
    license.write_text(license.read_text() + "\nCommons Clause: the Software may not be sold or used commercially.\n")
    findings = check(package(catalog), luac)
    assert summary(findings) == [("extensions/example/LICENSE", 1, "license")]
    assert findings[0].message.startswith("LICENSE is not the text of MIT")


def test_restriction_in_a_blank_of_the_template_fails(catalog, luac):
    license = package(catalog) / "LICENSE"
    license.write_text(license.read_text().replace("Moneten maintainers", "Moneten maintainers. No commercial use"))
    findings = check(package(catalog), luac)
    assert summary(findings) == [("extensions/example/LICENSE", 1, "license")]
    assert findings[0].message == "LICENSE adds the words 'commercial' to the text of MIT. A catalog package may not restrict its license."


def test_proprietary_text_that_quotes_a_license_phrase_fails(catalog, luac):
    (package(catalog) / "LICENSE").write_text('All rights reserved. The phrase "Permission is hereby granted, free of charge, to any person obtaining a copy" does not apply.\n')
    assert summary(check(package(catalog), luac)) == [("extensions/example/LICENSE", 1, "license")]


def test_long_line_fails(catalog, luac):
    code = "local t = {" + ", ".join(str(n) for n in range(200)) + "}"
    line = append_lua(catalog, code)
    findings = check(package(catalog), luac)
    assert summary(findings) == [(LUA, line, "obfuscation")]
    assert findings[0].message == f"the line has {len(code)} characters. The limit is 500."


def test_bytecode_fails(catalog, luac):
    script = package(catalog) / "Example.lua"
    subprocess.run([luac, "-o", str(script), str(script)], check=True)
    assert summary(check(package(catalog), luac)) == [(LUA, 1, "obfuscation")]


def test_escaped_byte_string_fails(catalog, luac):
    line = append_lua(catalog, 'local blob = "' + "\\1" * 201 + '"')
    assert summary(check(package(catalog), luac)) == [(LUA, line, "obfuscation")]


def test_high_entropy_string_fails(catalog, luac):
    alphabet = "".join(chr(c) for c in range(33, 127) if chr(c) not in "\\\"")
    noise = "".join(alphabet[(n * 37 + n // 7) % len(alphabet)] for n in range(400))
    line = append_lua(catalog, "local key = [[\n" + "\n".join(noise[i : i + 80] for i in range(0, 400, 80)) + "]]")
    findings = check(package(catalog), luac)
    assert [(f.path, f.rule) for f in findings] == [(LUA, "obfuscation")]
    assert line <= findings[0].line <= line + 5
    assert "looks encoded or encrypted" in findings[0].message


def hex_digest_pieces(count):
    return [hashlib.sha256(str(n).encode()).hexdigest() for n in range(count)]


@pytest.mark.parametrize("code, message", [
    ('local s = "\\\n' + ("\\104" * 60 + "\\\n") * 4 + '"', "writes 240 bytes as escapes"),
    ("local s = " + " ..\n".join(['"' + "\\x68" * 50 + '"'] * 5), "writes 250 bytes as escapes"),
    ("\n".join(f'local {name} = "' + "a\\104" * 70 + '"' for name in "abc"), "writes 210 bytes as escapes"),
    ("local s = " + " ..\n".join(f'"{piece}"' for piece in hex_digest_pieces(6)), "holds 384 characters of hex or base64"),
    ("local s = " + " ..\n".join(f'"{piece}"' for piece in [base64.b64encode(hashlib.sha512(str(n).encode()).digest()).decode() for n in range(4)]), "holds 352 characters of hex or base64"),
    ("local s = " + " ..\n".join("string.char(" + ",".join(str(100 + n) for n in range(30)) + ")" for _ in range(3)), "passes 90 bytes as numbers"),
    ("local s = " + " ..\n".join("string.char(" + ",".join(str(100 + n) for n in range(7)) + ")" for _ in range(10)), "passes 70 bytes as numbers"),
    ("local c = string.char\nlocal s = " + " ..\n".join("c(" + ",".join(str(100 + n) for n in range(3)) + ")" for _ in range(22)), "passes 66 bytes as numbers"),
])
def test_encoded_data_spread_over_lines_and_pieces_fails(catalog, luac, code, message):
    line = append_lua(catalog, code)
    findings = [f for f in check(package(catalog), luac) if message in f.message]
    assert [(f.rule, f.warning) for f in findings] == [("obfuscation", False)]
    assert line <= findings[0].line <= line + code.count("\n")
    assert run_cli(catalog).returncode == 1


def test_real_iban_in_recording_fails(catalog, luac):
    fixture = package(catalog) / "recording" / "fixture.json"
    lines = fixture.read_text().splitlines()
    number = next(n for n, text in enumerate(lines, 1) if "DE02120300000000202051" in text)
    fixture.write_text(fixture.read_text().replace("DE02120300000000202051", "DE89370400440532013000"))
    findings = check(package(catalog), luac)
    assert summary(findings) == [(FIXTURE, number, "personal-data")]
    assert "DE89370400440532013000" in findings[0].message


def test_email_outside_example_domains_fails(catalog, luac):
    expected = package(catalog) / "recording" / "expected.json"
    expected.write_text(expected.read_text().replace('"owner": "Erika Mustermann"', '"owner": "erika@mail.de"'))
    assert summary(check(package(catalog), luac)) == [("extensions/example/recording/expected.json", 5, "personal-data")]


MANIFEST_CASES = json.loads((TOOLS.parent / "schema" / "fixtures" / "manifest-cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", MANIFEST_CASES, ids=[case["name"] for case in MANIFEST_CASES])
def test_the_schema_judges_each_shared_manifest_case_as_the_app_does(catalog, luac, case):
    edit_manifest(catalog, **case["change"])
    schema_findings = [f for f in check(package(catalog), luac) if f.rule == "schema"]
    assert (schema_findings == []) == case["valid"], schema_findings


def test_wildcard_host_fails_the_schema(catalog, luac):
    edit_manifest(catalog, hosts=["*.bank.example"])
    findings = check(package(catalog), luac)
    assert summary(findings) == [(MANIFEST, 1, "schema")]
    assert findings[0].message.startswith("hosts/0:")


def test_unexpected_file_fails(catalog, luac):
    (package(catalog) / "helper.luac").write_bytes(b"\x1bLua")
    assert summary(check(package(catalog), luac)) == [("extensions/example/helper.luac", 0, "layout")]


def test_new_host_needs_sign_off(catalog, luac):
    edit_manifest(catalog, hosts=["api.bank.example", "login.bank.example", "www.bank.example"], version="1.1")
    findings = check(package(catalog), luac, base="HEAD")
    assert [(f.path, f.rule, f.message, f.label) for f in findings] == [(MANIFEST, "new-host", "adds the host login.bank.example.", "hosts-approved")]


def test_changed_script_needs_a_higher_version(catalog, luac):
    append_lua(catalog, "local unused = 1")
    assert summary(check(package(catalog), luac, base="HEAD")) == [(MANIFEST, 1, "version")]
    edit_manifest(catalog, version="1.0.1")
    assert check(package(catalog), luac, base="HEAD") == []


def test_changed_recording_needs_no_new_version(catalog, luac):
    expected = package(catalog) / "recording" / "expected.json"
    expected.write_text(expected.read_text().replace("Girokonto", "Konto"))
    assert check(package(catalog), luac, base="HEAD") == []


def run_cli(catalog, *args):
    return subprocess.run(
        [sys.executable, str(TOOLS / "check_package.py"), "--root", str(catalog), *args],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "LUAC": check_package.luac_path()},
    )


def test_cli_fails_on_errors_and_prints_one_line_per_finding(catalog):
    line = append_lua(catalog, 'os.remove("x")')
    result = run_cli(catalog)
    assert result.returncode == 1
    assert result.stdout == f"{LUA}:{line}: forbidden: os.remove is not available.\n"


def test_cli_passes_io_warning_but_sign_off_needs_the_label(catalog):
    line = append_lua(catalog, "local open = io.open")
    warning = f"{LUA}:{line}: io: reads io.open. Moneten gives scripts an io table without functions, so the value is nil."
    checks = run_cli(catalog)
    assert (checks.returncode, checks.stdout) == (0, f"{warning} Needs the label io-acknowledged from a maintainer.\n")
    assert run_cli(catalog, "--sign-off", "--base", "HEAD", "--changed").returncode == 1
    labelled = run_cli(catalog, "--sign-off", "--base", "HEAD", "--changed", "--labels", "io-acknowledged")
    assert (labelled.returncode, labelled.stdout) == (0, f"{warning} Acknowledged by the label io-acknowledged.\n")


def test_cli_refuses_a_deleted_package(catalog):
    shutil.rmtree(package(catalog))
    result = run_cli(catalog, "--base", "HEAD")
    assert result.returncode == 1
    assert result.stdout.startswith("extensions/example:0: removed:")


def test_cli_refuses_status_for_an_unknown_package(catalog):
    (catalog / "status.json").write_text('{"ghost": {"state": "blocked", "note": "Sends the password to another host."}}\n')
    result = run_cli(catalog)
    assert (result.returncode, result.stdout) == (1, "status.json:1: schema: ghost has no folder in extensions/.\n")


def test_duplicate_key_in_the_manifest_fails(catalog, luac):
    path = package(catalog) / "manifest.json"
    text = path.read_text()
    path.write_text(text.replace('"hosts": [', '"hosts": ["tracker.example"],\n  "hosts": [', 1))
    findings = check(package(catalog), luac)
    assert summary(findings) == [(MANIFEST, 0, "schema")]
    assert "hosts" in findings[0].message


def test_two_services_with_the_same_name_fail(catalog, luac):
    manifest = json.loads((package(catalog) / "manifest.json").read_text())
    edit_manifest(catalog, services=manifest["services"] * 2)
    findings = check(package(catalog), luac)
    assert summary(findings) == [(MANIFEST, 1, "schema")]
    assert "Example Bank" in findings[0].message


def test_a_service_without_login_fields_fails(catalog, luac):
    edit_manifest(catalog, services=[{"name": "Example Bank", "login": []}])
    findings = check(package(catalog), luac)
    assert summary(findings) == [(MANIFEST, 1, "schema")]
    assert findings[0].message.startswith("services/0/login:")


def symlink(path, target):
    path.unlink()
    path.symlink_to(target)


def hard_link(path, target):
    path.unlink()
    os.link(target, path)


def fifo(path, target):
    path.unlink()
    os.mkfifo(path)


@pytest.mark.parametrize("name", ["README.md", "manifest.json", "recording/fixture.json"])
@pytest.mark.parametrize("replace", [symlink, hard_link, fifo])
def test_a_package_file_that_is_not_a_regular_file_fails_unread(catalog, luac, tmp_path, name, replace):
    secret = tmp_path / "environ"
    secret.write_text("INDEX_SIGNING_KEY=secret\n")
    replace(package(catalog) / name, secret)
    findings = check(package(catalog), luac)
    assert summary(findings) == [(f"extensions/example/{name}", 0, "layout")]
    assert "not a regular file" in findings[0].message


def test_a_package_folder_that_is_a_symbolic_link_fails(catalog):
    (catalog / "extensions" / "mirror").symlink_to(package(catalog))
    result = run_cli(catalog)
    assert result.returncode == 1
    assert result.stdout.startswith("extensions/mirror:0: layout: ")


def test_a_symbolic_link_outside_the_packages_fails(catalog, tmp_path):
    (catalog / "schema").mkdir()
    (catalog / "schema" / "leak.json").symlink_to(tmp_path / "environ")
    git(catalog, "add", "-A")
    result = run_cli(catalog)
    assert result.returncode == 1
    assert result.stdout.startswith("schema/leak.json:0: layout: ")
