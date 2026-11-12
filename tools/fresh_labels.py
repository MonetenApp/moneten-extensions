#!/usr/bin/env python3
"""Print the sign-off labels of a pull request that a maintainer set after its newest push.

Usage:
  tools/fresh_labels.py REPOSITORY PULL_REQUEST HEAD_SHA

Reads GITHUB_TOKEN. A label set before the newest push approves code that is no longer
the head, so it does not count. The time of a push is when GitHub created the first
pull_request workflow run for the head commit after the newest run for another commit,
because commit dates come from the author, and a force-push can bring back a commit
that had runs before.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
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


def head_pushed_at(runs: list[dict], head: str, repository: str, branch: str) -> str | None:
    """When the branch of the pull request last moved to head, or None if no run shows it."""
    since = None
    for run in sorted(runs, key=lambda r: r["created_at"]):
        same_branch = run["head_branch"] == branch and (run.get("head_repository") or {}).get("full_name") == repository
        if run["event"] != "pull_request" or not same_branch:
            continue
        if run["head_sha"] != head:
            since = None
        elif since is None:
            since = run["created_at"]
    return since


def get(url: str, token: str) -> tuple[object, str]:
    """Returns the JSON of url and the URL of its next page, or ""."""
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        links = response.headers.get("Link", "")
        return json.load(response), next((m[1] for m in re.finditer(r'<([^>]+)>;\s*rel="next"', links)), "")


def get_all(url: str, token: str, key: str | None = None) -> list[dict]:
    items: list[dict] = []
    while url:
        page, url = get(url, token)
        items += page[key] if key else page
    return items


def main(argv: list[str]) -> int:
    repository, number, head = argv
    token = os.environ["GITHUB_TOKEN"]
    api = f"https://api.github.com/repos/{repository}"
    pull, _ = get(f"{api}/pulls/{number}", token)
    repository_of_head = (pull["head"]["repo"] or {}).get("full_name", "")
    branch = pull["head"]["ref"]
    runs = get_all(f"{api}/actions/runs?{urllib.parse.urlencode({'branch': branch, 'event': 'pull_request', 'per_page': 100})}", token, "workflow_runs")
    pushed_at = head_pushed_at(runs, head, repository_of_head, branch)
    if pushed_at is None:
        print("::error::No workflow run shows the push of the head commit, so the time of the push is unknown.", file=sys.stderr)
        return 1
    fresh, stale = split_labels(get_all(f"{api}/issues/{number}/events?per_page=100", token), pushed_at)
    for name in stale:
        print(f"::warning title={name} is stale::The label {name} was set before the push of {head[:7]} at {pushed_at}. A maintainer must remove it and set it again after reading the new commits.", file=sys.stderr)
    print(",".join(fresh))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
