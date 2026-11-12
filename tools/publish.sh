#!/usr/bin/env bash
# Checks that index.json on gh-pages is signed by keys/current.pub or keys/next.pub,
# builds and signs the next index, checks its signature against the same keys,
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

links_in() {
	git -C "$1" ls-files -s | awk '$1 == "120000" || $1 == "160000" { sub(/^[^\t]*\t/, ""); print }'
}

signed_by_a_catalog_key() {
	for public in keys/current.pub keys/next.pub; do
		if openssl pkeyutl -verify -pubin -inkey "$public" -rawin -in "$1/index.json" -sigfile "$1/index.json.sig" >/dev/null 2>&1; then
			return 0
		fi
	done
	return 1
}

links="$(links_in .)"
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
	trap 'git worktree remove --force "$site"' EXIT
	links="$(links_in "$site")"
	if [[ -n "$links" ]]; then
		echo "gh-pages holds symbolic links or submodules, which this run would publish again. Nothing was published:" >&2
		echo "$links" >&2
		exit 1
	fi
	if ! published="$(index_version "$site/index.json" 2>/dev/null)"; then
		echo "gh-pages has no readable index.json, so the published version is unknown. Nothing was published." >&2
		exit 1
	fi
	if ! signed_by_a_catalog_key "$site"; then
		echo "index.json on gh-pages has no valid signature by keys/current.pub or keys/next.pub, so its version and packages cannot be trusted. Nothing was published." >&2
		exit 1
	fi
elif [[ $status -eq 2 ]]; then
	git worktree add -q --orphan -b "publish-$$" "$site"
	trap 'git worktree remove --force "$site"' EXIT
else
	echo "Cannot read the branch gh-pages of origin, so the published version is unknown. Nothing was published." >&2
	exit 1
fi

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
if ! signed_by_a_catalog_key "$site"; then
	echo "The key file signs with neither keys/current.pub nor keys/next.pub. Nothing was published. See docs/set-up-signing.md." >&2
	exit 1
fi

mkdir -p "$site/schema"
cp schema/*.json "$site/schema/"
echo extensions.monetenapp.com >"$site/CNAME"
touch "$site/.nojekyll"
git -C "$site" add -A
git -C "$site" -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
	commit -q -m "Publish index $version from $(git rev-parse --short HEAD)"
git -C "$site" push -q origin HEAD:refs/heads/gh-pages
echo "Published index $version."
