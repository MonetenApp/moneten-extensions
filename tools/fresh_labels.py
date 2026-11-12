#!/usr/bin/env python3
"""Print the sign-off labels of a pull request that a maintainer stands behind for its head commit.

Usage:
  tools/fresh_labels.py REPOSITORY PULL_REQUEST HEAD_SHA

Reads GITHUB_TOKEN. A label counts only while a maintainer's approving review names HEAD_SHA.
GitHub does not let authors approve their own pull requests, so on a maintainer's own pull
request a review of the author that names HEAD_SHA, such as a comment, counts instead. A review
names the commit it read, so a later push, a force-push back to an older commit, or a commit
that started no workflow run cannot carry a label to code that no maintainer read.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

SIGN_OFF_LABELS = ("hosts-approved", "io-acknowledged")
MAINTAINER_PERMISSIONS = {"admin", "write"}
DECIDING_STATES = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}


def approvers_of(reviews: list[dict], head: str) -> set[str]:
    """The logins whose newest deciding review approves head. A comment changes no decision."""
    decision: dict[str, dict] = {}
    for review in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
        if review["state"] in DECIDING_STATES and review.get("user"):
            decision[review["user"]["login"]] = review
    return {login for login, review in decision.items() if review["state"] == "APPROVED" and review["commit_id"] == head}


def get(url: str, token: str) -> tuple[object, str]:
    """Returns the JSON of url and the URL of its next page, or ""."""
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        links = response.headers.get("Link", "")
        return json.load(response), next((m[1] for m in re.finditer(r'<([^>]+)>;\s*rel="next"', links)), "")


def get_all(url: str, token: str) -> list[dict]:
    items: list[dict] = []
    while url:
        page, url = get(url, token)
        items += page
    return items


def main(argv: list[str]) -> int:
    repository, number, head = argv
    token = os.environ["GITHUB_TOKEN"]
    api = f"https://api.github.com/repos/{repository}"

    def is_maintainer(login: str) -> bool:
        permission, _ = get(f"{api}/collaborators/{login}/permission", token)
        return permission.get("permission") in MAINTAINER_PERMISSIONS

    pull, _ = get(f"{api}/pulls/{number}", token)
    labels = [name for name in SIGN_OFF_LABELS if name in {label["name"] for label in pull["labels"]}]
    if not labels:
        print("")
        return 0
    reviews = get_all(f"{api}/pulls/{number}/reviews?per_page=100", token)
    author = pull["user"]["login"]
    readers = approvers_of(reviews, head)
    if any(r["user"] and r["user"]["login"] == author and r["commit_id"] == head and r["state"] in ("COMMENTED", "APPROVED") for r in reviews):
        readers.add(author)
    if any(is_maintainer(login) for login in sorted(readers)):
        print(",".join(labels))
        return 0
    for name in labels:
        print(f"::warning title={name} waits for an approval::No maintainer approved {head[:7]}, so the label {name} does not count yet. Approve the pull request, or as its author leave a review with Comment, then set the label again or re-run this job.", file=sys.stderr)
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
