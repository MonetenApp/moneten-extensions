#!/usr/bin/env bash
# Fetches the release of ext that tools/ext.lock pins, and checks it before anything runs it.
#
# Usage: tools/fetch_ext.sh DIR [ZIP]
#
# VERSION, COMMIT, URL, SHA256: the fields of tools/ext.lock, as tools/ext_lock.py prints them.
# DIR: the script writes the zip to DIR/ext.zip and the binary to DIR/ext/ext, and replaces both.
# ZIP: a local zip to check in place of a download of URL. The tests use it to run without a network.
#
# The checks run in this order, and the first one that fails stops the script: the SHA-256 of the zip,
# its one entry, a regular file named ext, the extracted file, the signature with the Developer ID of
# the project, and the version and commit that ext --version names. The zip is inspected before it is
# extracted, because unzip follows no rule of ours: it writes a link, and it turns ../ext into ext.
set -euo pipefail

# The team ID of the Developer ID of the project. The two fields admit only a Developer ID Application
# certificate: the first marks the Developer ID intermediate, the second the leaf. Without them, the
# Apple Development and Apple Distribution certificates of the team would pass as well.
TEAM=39945LJS7U
REQUIREMENT="=anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] exists and certificate leaf[field.1.2.840.113635.100.6.1.13] exists and certificate leaf[subject.OU] = \"$TEAM\""

fail() {
	echo "::error file=tools/ext.lock::$1" >&2
	exit 1
}

: "${VERSION:?}" "${COMMIT:?}" "${URL:?}" "${SHA256:?}"
if [[ $# -lt 1 || $# -gt 2 ]]; then
	echo "usage: tools/fetch_ext.sh DIR [ZIP]" >&2
	exit 2
fi
dir="$1"
zip="$dir/ext.zip"
bin="$dir/ext/ext"

mkdir -p "$dir"
rm -rf "$zip" "$dir/ext"
if [[ $# -eq 2 ]]; then
	cp "$2" "$zip"
else
	curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$zip" "$URL"
fi

actual="$(shasum -a 256 "$zip" | cut -d' ' -f1)"
[[ "$actual" == "$SHA256" ]] || fail "The zip has the SHA-256 $actual, not the SHA-256 in tools/ext.lock."

# The trailing dot keeps a newline at the end of a name, which $(...) would drop. It follows only a
# zipinfo that succeeded, so a failed zipinfo fails the script and never passes on its partial output.
entries="$(zipinfo -1 "$zip" && echo .)" || fail "zipinfo cannot read the zip."
[[ "$entries" == $'ext\n.' ]] || fail "The zip must hold exactly one entry, ext, and no path or second entry."
listing="$(zipinfo -s "$zip" ext)" || fail "zipinfo cannot list the entry ext."
[[ "$listing" == -* ]] || fail "The entry ext must be a regular file, not a link or a folder: $listing"

mkdir "$dir/ext"
unzip -q "$zip" ext -d "$dir/ext" || fail "unzip could not extract ext."
[[ "$(ls -A "$dir/ext")" == ext && -f "$bin" && ! -L "$bin" ]] || fail "The zip did not extract to one regular file ext."

codesign --verify --strict -R "$REQUIREMENT" "$bin" || fail "ext is not signed with the Developer ID of team $TEAM."

line="$("$bin" --version)"
echo "$line"
[[ "$line" == "ext $VERSION (commit $COMMIT), API version "* ]] || fail "ext names another version or commit than tools/ext.lock."
