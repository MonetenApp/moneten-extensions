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



def test_a_tracked_symbolic_link_stops_the_publish(repo, tmp_path):
    work, key, origin = repo
    (tmp_path / "environ").write_text("INDEX_SIGNING_KEY=secret\n")
    (work / "schema" / "leak.json").symlink_to(tmp_path / "environ")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "leak")
    git(work, "push", "-q", "origin", "main")
    result = publish(work, key)
    assert result.returncode == 1
    assert "schema/leak.json" in result.stderr
    assert published_version(origin) is None


def push_to_gh_pages(work, change):
    git(work, "fetch", "-q", "origin", "gh-pages")
    git(work, "checkout", "-q", "-B", "pages", "FETCH_HEAD")
    change(work)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "tamper")
    git(work, "push", "-q", "origin", "pages:gh-pages")
    git(work, "checkout", "-q", "main")
    return run(work, "git", "rev-parse", "pages").stdout.strip()


def raise_version(work):
    index = json.loads((work / "index.json").read_text())
    index["version"] = 99
    (work / "index.json").write_text(json.dumps(index, indent=2) + "\n")


def test_published_index_without_a_valid_signature_is_not_trusted(repo):
    work, key, origin = repo
    assert publish(work, key).returncode == 0
    tampered = push_to_gh_pages(work, raise_version)
    result = publish(work, key)
    assert result.returncode == 1
    assert "index.json on gh-pages has no valid signature" in result.stderr
    assert run(origin, "git", "rev-parse", "gh-pages").stdout.strip() == tampered


def test_symbolic_link_on_gh_pages_is_not_published_again(repo, tmp_path):
    work, key, origin = repo
    assert publish(work, key).returncode == 0
    tampered = push_to_gh_pages(work, lambda site: (site / "env").symlink_to("/proc/self/environ"))
    result = publish(work, key)
    assert result.returncode == 1
    assert "env" in result.stderr
    assert run(origin, "git", "rev-parse", "gh-pages").stdout.strip() == tampered


def test_key_rotation_publishes_at_every_step(repo, tmp_path):
    work, current, origin = repo
    following = tmp_path / "next.pem"
    assert publish(work, current).returncode == 0
    assert publish(work, following).returncode == 0
    newest = tmp_path / "newest.pem"
    run(tmp_path, "openssl", "genpkey", "-algorithm", "ed25519", "-out", str(newest))
    (work / "keys" / "next.pub").replace(work / "keys" / "current.pub")
    run(tmp_path, "openssl", "pkey", "-in", str(newest), "-pubout", "-out", str(work / "keys" / "next.pub"))
    git(work, "commit", "-q", "-am", "rotate the keys")
    git(work, "push", "-q", "origin", "main")
    result = publish(work, following)
    assert result.returncode == 0, result.stderr
    assert published_version(origin) == 3


def test_the_published_tree_is_copied_for_the_pages_deployment(repo, tmp_path):
    work, key, origin = repo
    copy = tmp_path / "pages"
    result = run(work, "bash", "tools/publish.sh", str(key), str(copy), check=False)
    assert result.returncode == 0, result.stderr
    published = run(origin, "git", "ls-tree", "-r", "--name-only", "gh-pages").stdout.split()
    assert sorted(p.relative_to(copy).as_posix() for p in copy.rglob("*") if p.is_file()) == sorted(published)
    assert (copy / "index.json").read_text() == run(origin, "git", "show", "gh-pages:index.json").stdout
