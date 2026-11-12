#!/usr/bin/env bash
# Builds and signs the index, checks the signature against keys/current.pub,
# and pushes the site to the gh-pages branch of origin.
# Usage: tools/publish.sh KEY_FILE
set -euo pipefail
key="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
cd "$(dirname "$0")/.."

for public in keys/current.pub keys/next.pub; do
	if ! openssl pkey -pubin -in "$public" -noout 2>/dev/null; then
		echo "$public is missing or is not a public key. See docs/set-up-signing.md." >&2
		exit 1
	fi
done

site="$(mktemp -d)/site"
if git fetch -q --depth 1 origin gh-pages 2>/dev/null; then
	git worktree add -q --detach "$site" FETCH_HEAD
else
	git worktree add -q --orphan -b "publish-$$" "$site"
fi
trap 'git worktree remove --force "$site"' EXIT

previous=""
if [[ -f "$site/index.json" ]]; then
	previous="$site/index.json"
fi
python3 tools/build_index.py --out "$site" ${previous:+--previous "$previous"} --key "$key"
openssl pkeyutl -verify -pubin -inkey keys/current.pub -rawin -in "$site/index.json" -sigfile "$site/index.json.sig"

mkdir -p "$site/schema"
cp schema/*.json "$site/schema/"
echo extensions.monetenapp.com >"$site/CNAME"
touch "$site/.nojekyll"
version="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' "$site/index.json")"
git -C "$site" add -A
git -C "$site" -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
	commit -q -m "Publish index $version from $(git rev-parse --short HEAD)"
git -C "$site" push -q origin HEAD:refs/heads/gh-pages
echo "Published index $version."
