import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import check_package  # noqa: E402


@pytest.fixture(scope="session")
def luac():
    return check_package.luac_path()


@pytest.fixture
def catalog(tmp_path):
    shutil.copytree(ROOT / "extensions" / "example", tmp_path / "extensions" / "example")
    (tmp_path / "status.json").write_text("{}\n")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "base")
    return tmp_path


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
