#!/usr/bin/env bash
set -euo pipefail

version=5.4.8
sha256=4f18ddae154e793e46eeab727c59ef1c0c0c2b744e7b94219710d76f530629ae
root="$(cd "$(dirname "$0")/.." && pwd)"
cache="$root/.cache"
luac="$cache/lua-$version/src/luac"

if [[ ! -x "$luac" ]]; then
	mkdir -p "$cache"
	tarball="$cache/lua-$version.tar.gz"
	# lua.org often resets connections. The mirror is the one lua.org lists.
	for url in "https://www.lua.org/ftp/lua-$version.tar.gz" "https://www.tecgraf.puc-rio.br/lua/mirror/ftp/lua-$version.tar.gz"; do
		curl -fsSL --retry 3 --retry-all-errors -o "$tarball" "$url" && break
	done
	actual="$(shasum -a 256 "$tarball" | cut -d' ' -f1)"
	if [[ "$actual" != "$sha256" ]]; then
		echo "lua-$version.tar.gz has SHA-256 $actual, expected $sha256" >&2
		exit 1
	fi
	tar -xzf "$tarball" -C "$cache"
	make -s -C "$cache/lua-$version" posix >/dev/null
fi
"$luac" -v

python3 -m pip install --quiet --require-hashes --only-binary :all: --requirement "$root/tools/requirements.txt"
