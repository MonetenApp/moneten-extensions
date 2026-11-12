#!/usr/bin/env bash
# Pushes OUT_DIR/site, which tools/publish.sh signed, to gh-pages of origin as one commit on top
# of the commit in OUT_DIR/parent. The commit holds exactly the files of the site.
# Usage: tools/push-site.sh OUT_DIR
set -euo pipefail
out="$(cd "$1" && pwd)"
cd "$(dirname "$0")/.."

parent="$(cat "$out/parent")"
if [[ -n "$parent" ]]; then
	git fetch -q --depth 1 origin gh-pages
	if [[ "$(git rev-parse FETCH_HEAD)" != "$parent" ]]; then
		echo "gh-pages moved after the signing run read it. Nothing was pushed. Run the workflow sign again." >&2
		exit 1
	fi
fi

git_dir="$(git rev-parse --absolute-git-dir)"
export GIT_INDEX_FILE="$(mktemp -d)/index"
GIT_DIR="$git_dir" git -C "$out/site" --work-tree=. add -A -f .
tree="$(GIT_DIR="$git_dir" git write-tree)"
unset GIT_INDEX_FILE
commit="$(GIT_AUTHOR_NAME="github-actions[bot]" GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com" \
	GIT_COMMITTER_NAME="github-actions[bot]" GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com" \
	git commit-tree "$tree" ${parent:+-p "$parent"} -m "Publish the index signed from $(git rev-parse --short HEAD)")"
git push -q origin "$commit:refs/heads/gh-pages"
echo "Pushed $(git rev-parse --short "$commit") to gh-pages."
