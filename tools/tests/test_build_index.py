import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
PUBLISHED = "2026-11-12T12:00:00Z"


@pytest.fixture
def keys(tmp_path):
    key, public = tmp_path / "key.pem", tmp_path / "public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(key)], check=True)
    subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(public)], check=True)
    return key, public


def build(catalog, out, *args):
    return subprocess.run(
        [sys.executable, str(TOOLS / "build_index.py"), "--root", str(catalog), "--out", str(out), "--published", PUBLISHED, *args],
        capture_output=True, text=True,
    )


def verifies(public, out):
    command = ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public), "-rawin", "-in", str(out / "index.json"), "-sigfile", str(out / "index.json.sig")]
    return subprocess.run(command, capture_output=True).returncode == 0


def add_second_script(catalog):
    folder = catalog / "extensions" / "example"
    (folder / "Parse.lua").write_text("ParseAmount = function(text) return tonumber(text) end\n")
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["files"] = ["Parse.lua", "Example.lua"]
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return folder


def test_each_build_raises_the_version_by_one(catalog, tmp_path):
    out = tmp_path / "site"
    assert build(catalog, out).returncode == 0
    assert json.loads((out / "index.json").read_text())["version"] == 1
    assert build(catalog, out, "--previous", str(out / "index.json")).returncode == 0
    assert json.loads((out / "index.json").read_text())["version"] == 2


def test_index_lists_the_digest_of_every_file_of_a_two_script_package(catalog, tmp_path):
    folder = add_second_script(catalog)
    out = tmp_path / "site"
    assert build(catalog, out).returncode == 0
    entry = json.loads((out / "index.json").read_text())["extensions"][0]
    names = ["Example.lua", "LICENSE", "Parse.lua", "README.md", "manifest.json"]
    assert entry["files"] == [
        {"path": n, "size": (folder / n).stat().st_size, "sha256": hashlib.sha256((folder / n).read_bytes()).hexdigest()} for n in names
    ]
    assert entry["manifest"]["files"] == ["Parse.lua", "Example.lua"]
    assert (entry["id"], entry["status"]) == ("example", "active")
    for n in names:
        assert (out / "example" / "1.0" / n).read_bytes() == (folder / n).read_bytes()


def test_signature_verifies_and_one_changed_byte_breaks_it(catalog, tmp_path, keys):
    key, public = keys
    out = tmp_path / "site"
    assert build(catalog, out, "--key", str(key)).returncode == 0
    assert len((out / "index.json.sig").read_bytes()) == 64
    assert verifies(public, out)
    data = bytearray((out / "index.json").read_bytes())
    data[40] ^= 1
    (out / "index.json").write_bytes(bytes(data))
    assert not verifies(public, out)


def test_status_and_note_come_from_status_json(catalog, tmp_path):
    (catalog / "status.json").write_text('{"example": {"state": "blocked", "note": "Sends the password to another host."}}\n')
    out = tmp_path / "site"
    assert build(catalog, out).returncode == 0
    entry = json.loads((out / "index.json").read_text())["extensions"][0]
    assert (entry["status"], entry["note"]) == ("blocked", "Sends the password to another host.")


def test_changed_file_under_a_published_version_is_refused(catalog, tmp_path):
    out = tmp_path / "site"
    assert build(catalog, out).returncode == 0
    (catalog / "extensions" / "example" / "Example.lua").write_text("-- changed\n")
    result = build(catalog, out, "--previous", str(out / "index.json"))
    assert result.returncode == 1
    assert "example/1.0/Example.lua is already published with other content" in result.stderr
    assert json.loads((out / "index.json").read_text())["version"] == 1


def test_deleted_package_is_refused(catalog, tmp_path):
    out = tmp_path / "site"
    assert build(catalog, out).returncode == 0
    shutil.rmtree(catalog / "extensions" / "example")
    result = build(catalog, out, "--previous", str(out / "index.json"))
    assert result.returncode == 1
    assert "published packages have no folder: example" in result.stderr


def set_version(catalog, version):
    path = catalog / "extensions" / "example" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["version"] = version
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def test_lower_version_than_the_published_one_is_refused(catalog, tmp_path):
    out = tmp_path / "site"
    set_version(catalog, "1.1")
    assert build(catalog, out).returncode == 0
    set_version(catalog, "1.0")
    result = build(catalog, out, "--previous", str(out / "index.json"))
    assert result.returncode == 1
    assert "example has version 1.0, but 1.1 is already published" in result.stderr
    assert json.loads((out / "index.json").read_text())["version"] == 1


def test_version_with_a_final_newline_is_refused(catalog, tmp_path):
    path = catalog / "extensions" / "example" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["version"] = "1.0\n"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    out = tmp_path / "site"
    result = build(catalog, out)
    assert result.returncode == 1
    assert "extensions/0/manifest/version" in result.stderr
    assert not (out / "index.json").exists()


def test_a_symbolic_link_in_a_package_is_refused_and_nothing_is_written(catalog, tmp_path):
    secret = tmp_path / "environ"
    secret.write_text("INDEX_SIGNING_KEY=secret\n")
    readme = catalog / "extensions" / "example" / "README.md"
    readme.unlink()
    readme.symlink_to(secret)
    out = tmp_path / "site"
    result = build(catalog, out)
    assert result.returncode == 1
    assert "example/README.md is not a regular file" in result.stderr
    assert not out.exists()
