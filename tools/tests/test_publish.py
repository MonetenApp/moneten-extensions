import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def run(cwd, *args, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


def git(cwd, *args, check=True):
    return run(cwd, "git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args, check=check)


@pytest.fixture
def repo(tmp_path):
    """A clone of a catalog whose origin is a local bare repository, with throwaway keys."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    run(tmp_path, "git", "init", "-q", "--bare", "-b", "main", str(origin))
    work.mkdir()
    for name in ("extensions", "schema", "tools", "status.json"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, work / name, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        else:
            shutil.copy(source, work / name)
    (work / "keys").mkdir()
    key = tmp_path / "current.pem"
    run(tmp_path, "openssl", "genpkey", "-algorithm", "ed25519", "-out", str(key))
    run(tmp_path, "openssl", "genpkey", "-algorithm", "ed25519", "-out", str(tmp_path / "next.pem"))
    run(tmp_path, "openssl", "pkey", "-in", str(key), "-pubout", "-out", str(work / "keys" / "current.pub"))
    run(tmp_path, "openssl", "pkey", "-in", str(tmp_path / "next.pem"), "-pubout", "-out", str(work / "keys" / "next.pub"))
    git(work, "init", "-q", "-b", "main")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "catalog")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    return work, key, origin


def publish(work, key):
    return run(work, "bash", "tools/publish.sh", str(key), check=False)


def published_version(origin):
    shown = run(origin, "git", "show", "gh-pages:index.json", check=False)
    return json.loads(shown.stdout)["version"] if shown.returncode == 0 else None


def test_each_publish_raises_the_published_version(repo):
    work, key, origin = repo
    assert publish(work, key).returncode == 0
    assert publish(work, key).returncode == 0
    assert published_version(origin) == 2


def test_commit_older_than_main_is_not_signed(repo):
    work, key, origin = repo
    assert publish(work, key).returncode == 0
    old = git(work, "rev-parse", "HEAD").stdout.strip()
    (work / "status.json").write_text('{"example": {"state": "blocked", "note": "Sends the password to another host."}}\n')
    git(work, "commit", "-q", "-am", "block example")
    git(work, "push", "-q", "origin", "main")
    git(work, "checkout", "-q", old)
    result = publish(work, key)
    assert result.returncode == 1
    assert "is not the newest main" in result.stderr
    assert published_version(origin) == 1


def test_gh_pages_without_an_index_is_not_overwritten(repo):
    work, key, origin = repo
    git(work, "checkout", "-q", "--orphan", "pages")
    git(work, "rm", "-q", "-rf", ".")
    (work / "README.md").write_text("placeholder\n")
    git(work, "add", "README.md")
    git(work, "commit", "-q", "-m", "pages")
    git(work, "push", "-q", "origin", "pages:gh-pages")
    git(work, "checkout", "-q", "main")
    result = publish(work, key)
    assert result.returncode == 1
    assert "gh-pages has no readable index.json" in result.stderr
    assert published_version(origin) is None

