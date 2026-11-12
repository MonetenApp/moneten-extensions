#!/usr/bin/env python3
"""Print the sign-off labels of a pull request that a maintainer set after its newest push.

Usage:
  tools/fresh_labels.py REPOSITORY PULL_REQUEST HEAD_SHA

Reads GITHUB_TOKEN. A label set before the newest push approves code that is no longer
the head, so it does not count. The time of a push is when GitHub created the first
workflow run for its head commit, because commit dates come from the author.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

SIGN_OFF_LABELS = ("hosts-approved", "io-acknowledged")


def labelled_at(events: list[dict]) -> dict[str, str]:
    """Maps each label the pull request has now to the time it was last set."""
    times: dict[str, str] = {}
    for event in sorted(events, key=lambda e: e["created_at"]):
        name = (event.get("label") or {}).get("name")
        if event["event"] == "labeled":
            times[name] = event["created_at"]
        elif event["event"] == "unlabeled":
            times.pop(name, None)
    return times


def split_labels(events: list[dict], head_pushed_at: str) -> tuple[list[str], list[str]]:
    """Returns the sign-off labels set after the push, and those set before it."""
    times = labelled_at(events)
    fresh = [name for name in SIGN_OFF_LABELS if times.get(name, "") > head_pushed_at]
    stale = [name for name in SIGN_OFF_LABELS if name in times and name not in fresh]
    return fresh, stale


def get_all(url: str, token: str, key: str | None = None) -> list[dict]:
    items: list[dict] = []
    while url:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            page = json.load(response)
            links = response.headers.get("Link", "")
        items += page[key] if key else page
        url = next((m[1] for m in re.finditer(r'<([^>]+)>;\s*rel="next"', links)), "")
    return items


def main(argv: list[str]) -> int:
    repository, number, head = argv
    token = os.environ["GITHUB_TOKEN"]
    api = f"https://api.github.com/repos/{repository}"
    runs = get_all(f"{api}/actions/runs?head_sha={head}&event=pull_request&per_page=100", token, "workflow_runs")
    if not runs:
        print("::error::No workflow run exists for the head commit, so the time of the push is unknown.", file=sys.stderr)
        return 1
    head_pushed_at = min(run["created_at"] for run in runs)
    fresh, stale = split_labels(get_all(f"{api}/issues/{number}/events?per_page=100", token), head_pushed_at)
    for name in stale:
        print(f"::warning title={name} is stale::The label {name} was set before the push of {head[:7]} at {head_pushed_at}. A maintainer must remove it and set it again after reading the new commits.", file=sys.stderr)
    print(",".join(fresh))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
