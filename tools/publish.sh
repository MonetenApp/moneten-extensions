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

links="$(git ls-files -s | awk '$1 == "120000" || $1 == "160000" { sub(/^[^\t]*\t/, ""); print }')"
if [[ -n "$links" ]]; then
	echo "The repository holds symbolic links or submodules, which could publish files from outside it. Nothing was published:" >&2
	echo "$links" >&2
	exit 1
fi

git fetch -q origin main
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse FETCH_HEAD)" ]]; then
	echo "HEAD $(git rev-parse --short HEAD) is not the newest main $(git rev-parse --short FETCH_HEAD). An older commit would publish older packages under a new index version, so only the newest main is signed." >&2
	exit 1
fi

index_version() {
	python3 -c 'import json, sys; v = json.load(open(sys.argv[1]))["version"]; assert type(v) is int; print(v)' "$1"
}

site="$(mktemp -d)/site"
published=0
status=0
git ls-remote -q --exit-code origin refs/heads/gh-pages >/dev/null || status=$?
if [[ $status -eq 0 ]]; then
	git fetch -q --depth 1 origin gh-pages
	git worktree add -q --detach "$site" FETCH_HEAD
	if ! published="$(index_version "$site/index.json" 2>/dev/null)"; then
		git worktree remove --force "$site"
		echo "gh-pages has no readable index.json, so the published version is unknown. Nothing was published." >&2
		exit 1
	fi
elif [[ $status -eq 2 ]]; then
	git worktree add -q --orphan -b "publish-$$" "$site"
else
	echo "Cannot read the branch gh-pages of origin, so the published version is unknown. Nothing was published." >&2
	exit 1
fi
trap 'git worktree remove --force "$site"' EXIT

previous=""
if [[ $status -eq 0 ]]; then
	previous="$site/index.json"
fi
python3 tools/build_index.py --out "$site" ${previous:+--previous "$previous"} --key "$key"
version="$(index_version "$site/index.json")"
if [[ $version -le $published ]]; then
	echo "The new index has version $version, but version $published is already published. Nothing was published." >&2
	exit 1
fi
openssl pkeyutl -verify -pubin -inkey keys/current.pub -rawin -in "$site/index.json" -sigfile "$site/index.json.sig"

mkdir -p "$site/schema"
cp schema/*.json "$site/schema/"
echo extensions.monetenapp.com >"$site/CNAME"
touch "$site/.nojekyll"
git -C "$site" add -A
git -C "$site" -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
	commit -q -m "Publish index $version from $(git rev-parse --short HEAD)"
git -C "$site" push -q origin HEAD:refs/heads/gh-pages
echo "Published index $version."
