"""tools/fetch_ext.sh on zips that the tests build. Each zip gets a matching SHA-256, so the later checks run."""
import hashlib
import os
import subprocess
import zipfile

import pytest

from conftest import ROOT

SCRIPT = ROOT / "tools" / "fetch_ext.sh"
VERSION, COMMIT = "0.1.0", "efda52da39625e4502541835e40b1b1bd7ee1dbe"
URL = "https://github.com/MonetenApp/Moneten/releases/download/ext-v0.1.0/ext-0.1.0-macos.zip"
VERSION_LINE = f"ext {VERSION} (commit {COMMIT}), API version 1"
FILE, LINK, FOLDER = 0o100755, 0o120777, 0o040755

pytestmark = pytest.mark.filterwarnings("ignore:Duplicate name:UserWarning")


def ext_script(line=VERSION_LINE):
    return f"#!/bin/sh\necho '{line}'\n".encode()


def build(path, *entries):
    """A zip with the given (name, data, mode) entries, in this order. zipfile warns on a duplicate but writes it."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, data, mode in entries:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, data)
    return path


def run(tmp_path, zip_path, sha256=None, codesign=None, zipinfo=None):
    """codesign: the exit status of a stub in place of codesign. zipinfo: the text of a stub in place of zipinfo."""
    env = dict(os.environ, VERSION=VERSION, COMMIT=COMMIT, URL=URL,
               SHA256=sha256 or hashlib.sha256(zip_path.read_bytes()).hexdigest())
    stubs = {}
    if codesign is not None:
        stubs["codesign"] = f"#!/bin/sh\nexit {codesign}\n"
    if zipinfo is not None:
        stubs["zipinfo"] = zipinfo
    if stubs:
        folder = tmp_path / "stubs"
        folder.mkdir()
        for name, text in stubs.items():
            (folder / name).write_text(text)
            (folder / name).chmod(0o755)
        env["PATH"] = f"{folder}{os.pathsep}{env['PATH']}"
    return subprocess.run([str(SCRIPT), str(tmp_path / "cache"), str(zip_path)], env=env,
                          capture_output=True, text=True)


@pytest.mark.parametrize("entries, message", [
    ([("ext", ext_script(), FILE), ("README", b"text\n", 0o100644)], "exactly one entry"),
    ([("ext", ext_script(), FILE), ("ext", ext_script(), FILE)], "exactly one entry"),
    ([("../ext", ext_script(), FILE)], "exactly one entry"),
    ([("/ext", ext_script(), FILE)], "exactly one entry"),
    ([("./ext", ext_script(), FILE)], "exactly one entry"),
    ([("bin/ext", ext_script(), FILE)], "exactly one entry"),
    ([("ext/", b"", FOLDER)], "exactly one entry"),
    ([("ext\n", ext_script(), FILE)], "exactly one entry"),
    ([("ext", b"/bin/sh", LINK)], "must be a regular file"),
    ([("ext", b"", FOLDER)], "must be a regular file"),
], ids=["extra entry", "duplicate", "parent path", "absolute path", "dot path", "subfolder", "folder ext/",
        "newline", "symlink", "folder ext"])
def test_a_zip_with_anything_but_one_regular_file_ext_fails_before_extraction(tmp_path, entries, message):
    result = run(tmp_path, build(tmp_path / "ext.zip", *entries), codesign=0)
    assert result.returncode == 1
    assert "::error file=tools/ext.lock::" in result.stderr and message in result.stderr
    assert not (tmp_path / "cache" / "ext").exists()
    assert not (tmp_path / "ext").exists()


def test_a_zip_with_another_hash_fails_before_it_is_read(tmp_path):
    result = run(tmp_path, build(tmp_path / "ext.zip", ("ext", ext_script(), FILE)), sha256="0" * 64, codesign=0)
    assert result.returncode == 1
    assert "not the SHA-256 in tools/ext.lock" in result.stderr
    assert not (tmp_path / "cache" / "ext").exists()


def test_a_failed_zipinfo_fails_before_extraction_even_when_it_prints_ext(tmp_path):
    marker = tmp_path / "ran"
    zip_path = build(tmp_path / "ext.zip", ("ext", f"#!/bin/sh\ntouch '{marker}'\necho '{VERSION_LINE}'\n".encode(), FILE))
    result = run(tmp_path, zip_path, codesign=0, zipinfo="#!/bin/sh\necho ext\nexit 9\n")
    assert result.returncode == 1
    assert "zipinfo cannot read the zip." in result.stderr
    assert not (tmp_path / "cache" / "ext").exists()
    assert not marker.exists()


def test_an_unsigned_ext_fails_the_signature_check_before_it_runs(tmp_path):
    marker = tmp_path / "ran"
    zip_path = build(tmp_path / "ext.zip", ("ext", f"#!/bin/sh\ntouch '{marker}'\n".encode(), FILE))
    result = run(tmp_path, zip_path)
    assert result.returncode == 1
    assert "ext is not signed with the Developer ID of team 39945LJS7U." in result.stderr
    assert not marker.exists()


def test_a_signed_ext_must_name_the_pinned_version_and_commit(tmp_path):
    zip_path = build(tmp_path / "ext.zip", ("ext", ext_script(f"ext {VERSION} (commit {'0' * 40}), API version 1"), FILE))
    result = run(tmp_path, zip_path, codesign=0)
    assert result.returncode == 1
    assert "ext names another version or commit than tools/ext.lock." in result.stderr


def test_a_good_zip_gives_one_regular_file_ext(tmp_path):
    result = run(tmp_path, build(tmp_path / "ext.zip", ("ext", ext_script(), FILE)), codesign=0)
    assert result.returncode == 0, result.stderr
    assert result.stdout == VERSION_LINE + "\n"
    extracted = tmp_path / "cache" / "ext"
    assert [p.name for p in extracted.iterdir()] == ["ext"]
    assert (extracted / "ext").is_file() and not (extracted / "ext").is_symlink()


def test_the_signature_check_names_the_developer_id_of_the_project():
    text = SCRIPT.read_text()
    assert "TEAM=39945LJS7U" in text
    assert ('REQUIREMENT="=anchor apple generic'
            ' and certificate 1[field.1.2.840.113635.100.6.2.6] exists'
            ' and certificate leaf[field.1.2.840.113635.100.6.1.13] exists'
            ' and certificate leaf[subject.OU] = \\"$TEAM\\""') in text
    assert 'codesign --verify --strict -R "$REQUIREMENT" "$bin"' in text
    assert "curl -fsSL --proto '=https' --tlsv1.2 --retry 3" in text
