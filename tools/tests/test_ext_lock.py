import pytest

import ext_lock
from conftest import ROOT

VERSION, COMMIT, SHA256 = "0.1.0", "efda52da39625e4502541835e40b1b1bd7ee1dbe", "0e651a3247551bb11a94f9693136b88816a328b139cf626c7036aee740ab1ee7"
URL = "https://github.com/MonetenApp/Moneten/releases/download/ext-v0.1.0/ext-0.1.0-macos.zip"


def lock(version=VERSION, commit=COMMIT, url=URL, sha256=SHA256):
    return f"# A comment.\n\nversion={version}\ncommit={commit}\nurl={url}\nsha256={sha256}\n"


def test_the_lock_of_the_repository_pins_a_release():
    fields = ext_lock.parse((ROOT / "tools" / "ext.lock").read_text())
    assert all(fields.values())
    assert fields["url"] == ext_lock.release_url(fields["version"])


def test_a_valid_lock_gives_each_field():
    assert ext_lock.parse(lock()) == {"version": VERSION, "commit": COMMIT, "url": URL, "sha256": SHA256}


def test_an_empty_lock_skips_the_job():
    assert ext_lock.parse(lock("", "", "", "")) == dict.fromkeys(ext_lock.FIELDS, "")


@pytest.mark.parametrize("text, message", [
    (lock(version=""), "version must"),
    (lock(commit="", url="", sha256=""), "commit must"),
    (lock(version="0.1"), "version must"),
    (lock(version="v0.1.0"), "version must"),
    (lock(version="0.01.0"), "version must"),
    (lock(version="0.1.0-beta"), "version must"),
    (lock(commit=COMMIT[:7]), "commit must"),
    (lock(commit=COMMIT.upper()), "commit must"),
    (lock(commit=COMMIT + "0"), "commit must"),
    (lock(commit="main"), "commit must"),
    (lock(url=URL.replace("https:", "http:")), "url must"),
    (lock(url=URL.replace("MonetenApp/Moneten", "someone/Moneten")), "url must"),
    (lock(url=URL.replace("ext-v0.1.0/", "ext-v0.2.0/")), "url must"),
    (lock(url=URL.replace("-macos.zip", "-macos.zip?x=1")), "url must"),
    (lock(url=URL + " "), "url must"),
    (lock(sha256=SHA256[:63]), "sha256 must"),
    (lock(sha256=SHA256.upper()), "sha256 must"),
    (lock(sha256="sha256:" + SHA256), "sha256 must"),
    (lock().replace(f"sha256={SHA256}\n", ""), "sha256 is missing"),
    (lock() + f"commit={COMMIT}\n", "repeats commit"),
    (lock() + "repository=someone/Moneten\n", "is not one of"),
    (lock().replace("version=", "version = "), "is not one of"),
    (lock() + "just text\n", "is not one of"),
])
def test_a_malformed_lock_fails(text, message):
    with pytest.raises(ext_lock.LockError, match=message):
        ext_lock.parse(text)


def test_main_prints_the_outputs_or_fails_with_an_annotation(tmp_path, capsys):
    good, bad = tmp_path / "good.lock", tmp_path / "bad.lock"
    good.write_text(lock())
    bad.write_text(lock(commit="b6ea16c"))
    assert ext_lock.main(["ext_lock.py", str(good)]) == 0
    assert capsys.readouterr().out == f"version={VERSION}\ncommit={COMMIT}\nurl={URL}\nsha256={SHA256}\n"
    assert ext_lock.main(["ext_lock.py", str(bad)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("::error file=tools/ext.lock::commit must")
