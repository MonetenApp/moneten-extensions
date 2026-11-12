import io
import json
import urllib.parse
import urllib.request

import fresh_labels
from fresh_labels import split_labels

PUSHED = "2026-11-12T14:00:00Z"


def event(kind, name, at):
    return {"event": kind, "label": {"name": name}, "created_at": at}


def test_label_set_after_the_newest_push_counts():
    events = [event("labeled", "hosts-approved", "2026-11-12T14:05:00Z")]
    assert split_labels(events, PUSHED) == (["hosts-approved"], [])


def test_label_set_before_the_newest_push_is_stale():
    events = [event("labeled", "hosts-approved", "2026-11-12T13:55:00Z"), event("labeled", "io-acknowledged", "2026-11-12T14:01:00Z")]
    assert split_labels(events, PUSHED) == (["io-acknowledged"], ["hosts-approved"])


def test_label_set_again_after_the_push_counts_again():
    events = [
        event("labeled", "hosts-approved", "2026-11-12T13:55:00Z"),
        event("unlabeled", "hosts-approved", "2026-11-12T14:02:00Z"),
        event("labeled", "hosts-approved", "2026-11-12T14:03:00Z"),
    ]
    assert split_labels(events, PUSHED) == (["hosts-approved"], [])


def test_removed_label_counts_neither_way():
    events = [event("labeled", "hosts-approved", "2026-11-12T14:01:00Z"), event("unlabeled", "hosts-approved", "2026-11-12T14:02:00Z")]
    assert split_labels(events, PUSHED) == ([], [])


A, B = "a" * 40, "b" * 40


def run(sha, at, branch="feature", repository="contributor/moneten-extensions", kind="pull_request"):
    return {"head_sha": sha, "created_at": at, "event": kind, "head_branch": branch, "head_repository": {"full_name": repository}}


class FakeGitHub:
    """Answers the REST calls of fresh_labels.py for pull request 7, with the filters the API applies."""

    def __init__(self, runs, events):
        self.runs, self.events = runs, events

    def __call__(self, request, timeout):
        url = urllib.parse.urlsplit(request.full_url)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path.endswith("/pulls/7"):
            body = {"number": 7, "head": {"sha": B, "ref": "feature", "repo": {"full_name": "contributor/moneten-extensions"}}}
        elif url.path.endswith("/actions/runs"):
            filters = {"head_sha": "head_sha", "event": "event", "branch": "head_branch"}
            body = {"workflow_runs": [r for r in self.runs if all(r[field] == query[param] for param, field in filters.items() if param in query)]}
        elif url.path.endswith("/issues/7/events"):
            body = self.events
        else:
            raise AssertionError(f"unexpected request {request.full_url}")
        return FakeResponse(body)


class FakeResponse(io.BytesIO):
    def __init__(self, body):
        super().__init__(json.dumps(body).encode())
        self.headers = {}


def fresh_after(monkeypatch, capsys, runs, events):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(urllib.request, "urlopen", FakeGitHub(runs, events))
    assert fresh_labels.main(["MonetenApp/moneten-extensions", "7", B]) == 0
    return capsys.readouterr()


# B adds a host, A is the approved commit, and B comes back after the label.
FORCE_PUSHED_BACK = [
    run(B, "2026-11-12T10:00:00Z"),
    run(A, "2026-11-12T10:10:00Z"),
    run(A, "2026-11-12T10:20:00Z"),
    run(B, "2026-11-12T10:30:00Z"),
    run("c" * 40, "2026-11-12T10:40:00Z", branch="other"),
    run("d" * 40, "2026-11-12T10:41:00Z", repository="someone-else/moneten-extensions"),
]


def test_label_set_on_an_older_commit_does_not_count_when_a_force_push_brings_back_a_newer_one(monkeypatch, capsys):
    out = fresh_after(monkeypatch, capsys, FORCE_PUSHED_BACK, [event("labeled", "hosts-approved", "2026-11-12T10:15:00Z")])
    assert out.out == "\n"
    assert "hosts-approved is stale" in out.err


def test_label_set_after_the_head_came_back_counts(monkeypatch, capsys):
    out = fresh_after(monkeypatch, capsys, FORCE_PUSHED_BACK, [event("labeled", "hosts-approved", "2026-11-12T10:35:00Z")])
    assert out.out == "hosts-approved\n"
