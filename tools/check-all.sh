#!/usr/bin/env bash
# Runs the tests of the tools and every check on every package.
# BASE: a git ref to compare with, for new hosts, version bumps, and deleted packages.
# EXT: an ext binary. Without it, the ext test check is skipped.
# LABELS: the comma-separated labels of the pull request.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pytest -q tools/tests
python3 tools/check_package.py ${BASE:+--base "$BASE"} ${EXT:+--ext "$EXT"} --labels "${LABELS:-}"
