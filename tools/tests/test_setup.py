import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARBALL = ROOT / ".cache" / "lua-5.4.8.tar.gz"
LYING_LUAC = '#!/bin/sh\necho "Lua 5.4.8  Copyright (C) 1994-2025 Lua.org, PUC-Rio"\n'


def test_a_luac_left_in_the_cache_is_rebuilt_from_the_verified_tarball(tmp_path):
    (tmp_path / "tools").mkdir()
    shutil.copy(ROOT / "tools" / "setup.sh", tmp_path / "tools" / "setup.sh")
    cache = tmp_path / ".cache"
    (cache / "lua-5.4.8" / "src").mkdir(parents=True)
    shutil.copy(TARBALL, cache / TARBALL.name)
    luac = cache / "lua-5.4.8" / "src" / "luac"
    luac.write_text(LYING_LUAC)
    luac.chmod(0o755)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "python3").write_text("#!/bin/sh\nexit 0\n")
    (stubs / "python3").chmod(0o755)
    env = {**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"}
    result = subprocess.run(["bash", "tools/setup.sh"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert luac.read_bytes()[:2] != b"#!"
    compiled = subprocess.run([str(luac), "-v"], capture_output=True, text=True)
    assert compiled.stdout.startswith("Lua 5.4.8 ")
