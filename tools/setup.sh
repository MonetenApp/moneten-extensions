#!/usr/bin/env bash
set -euo pipefail

version=5.4.8
sha256=4f18ddae154e793e46eeab727c59ef1c0c0c2b744e7b94219710d76f530629ae
root="$(cd "$(dirname "$0")/.." && pwd)"
cache="$root/.cache"
tarball="$cache/lua-$version.tar.gz"

sha256_of() {
	shasum -a 256 "$1" | cut -d' ' -f1
}

# Workflow runs share .cache, so a binary found there cannot be trusted. Only the tarball
# is reused, after its hash matches, and luac is built from it on every run.
mkdir -p "$cache"
if [[ ! -f "$tarball" || "$(sha256_of "$tarball")" != "$sha256" ]]; then
	# lua.org often resets connections. The mirror is the one lua.org lists.
	for url in "https://www.lua.org/ftp/lua-$version.tar.gz" "https://www.tecgraf.puc-rio.br/lua/mirror/ftp/lua-$version.tar.gz"; do
		curl -fsSL --retry 3 --retry-all-errors -o "$tarball" "$url" && break
	done
	actual="$(sha256_of "$tarball")"
	if [[ "$actual" != "$sha256" ]]; then
		echo "lua-$version.tar.gz has SHA-256 $actual, expected $sha256" >&2
		exit 1
	fi
fi
rm -rf "$cache/lua-$version"
tar -xzf "$tarball" -C "$cache"
make -s -C "$cache/lua-$version" posix >/dev/null
"$cache/lua-$version/src/luac" -v

python3 -m pip install --quiet --require-hashes --only-binary :all: --requirement "$root/tools/requirements.txt"
