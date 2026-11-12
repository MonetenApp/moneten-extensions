import io
import json
import urllib.parse
import urllib.request

import fresh_labels

REPOSITORY = "MonetenApp/moneten-extensions"
A, X = "a" * 40, "b" * 40
PERMISSIONS = {"maintainer": "admin", "helper": "write", "triager": "read", "contributor": "read"}


def review(user, state, commit, at):
    return {"user": {"login": user}, "state": state, "commit_id": commit, "submitted_at": at}


class FakeGitHub:
    """Answers the REST calls about pull request 7, whose head is X."""

    def __init__(self, reviews, author="contributor", head_repository="contributor/moneten-extensions"):
        self.reviews, self.author, self.head_repository = reviews, author, head_repository

    def __call__(self, request, timeout):
        path = urllib.parse.urlsplit(request.full_url).path.removeprefix(f"/repos/{REPOSITORY}")
        if path == "/pulls/7":
            body = {
                "number": 7, "user": {"login": self.author}, "labels": [{"name": "hosts-approved"}, {"name": "help wanted"}],
                "head": {"sha": X, "ref": "feature", "repo": {"full_name": self.head_repository}},
            }
        elif path == "/pulls/7/reviews":
            body = self.reviews
        elif path.startswith("/collaborators/") and path.endswith("/permission"):
            body = {"permission": PERMISSIONS.get(path.split("/")[2], "none")}
        else:
            raise AssertionError(f"unexpected request {request.full_url}")
        return FakeResponse(body)


class FakeResponse(io.BytesIO):
    def __init__(self, body):
        super().__init__(json.dumps(body).encode())
        self.headers = {}


def signed_off(monkeypatch, capsys, github):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(urllib.request, "urlopen", github)
    code = fresh_labels.main([REPOSITORY, "7", X])
    return code, capsys.readouterr()


def test_an_approval_of_another_commit_does_not_carry_the_label_to_the_head(monkeypatch, capsys):
    # X adds a host. A is pushed with [skip ci], approved and labelled, then X is force-pushed back.
    github = FakeGitHub([review("maintainer", "APPROVED", A, "2026-11-12T10:16:00Z")])
    code, out = signed_off(monkeypatch, capsys, github)
    assert (code, out.out) == (0, "\n")
    assert "hosts-approved" in out.err


def test_a_maintainer_approval_of_a_head_without_workflow_runs_carries_the_label(monkeypatch, capsys):
    github = FakeGitHub([review("maintainer", "APPROVED", X, "2026-11-12T10:16:00Z")])
    code, out = signed_off(monkeypatch, capsys, github)
    assert (code, out.out) == (0, "hosts-approved\n")


def test_an_approval_without_write_access_does_not_count(monkeypatch, capsys):
    github = FakeGitHub([review("triager", "APPROVED", X, "2026-11-12T10:16:00Z")])
    code, out = signed_off(monkeypatch, capsys, github)
    assert (code, out.out) == (0, "\n")


def test_an_approval_that_the_maintainer_took_back_does_not_count(monkeypatch, capsys):
    github = FakeGitHub([
        review("maintainer", "APPROVED", X, "2026-11-12T10:16:00Z"),
        review("maintainer", "COMMENTED", X, "2026-11-12T10:17:00Z"),
        review("maintainer", "CHANGES_REQUESTED", X, "2026-11-12T10:18:00Z"),
    ])
    code, out = signed_off(monkeypatch, capsys, github)
    assert (code, out.out) == (0, "\n")


def test_a_maintainer_author_binds_the_label_to_the_head_with_a_comment_review(monkeypatch, capsys):
    github = FakeGitHub([review("maintainer", "COMMENTED", X, "2026-11-12T10:16:00Z")], author="maintainer", head_repository=REPOSITORY)
    code, out = signed_off(monkeypatch, capsys, github)
    assert (code, out.out) == (0, "hosts-approved\n")


def test_a_label_on_a_maintainer_pull_request_does_not_survive_a_push(monkeypatch, capsys):
    # The author labels A, reviews A, and pushes X with a new host.
    github = FakeGitHub([review("maintainer", "COMMENTED", A, "2026-11-12T10:16:00Z")], author="maintainer", head_repository=REPOSITORY)
    code, out = signed_off(monkeypatch, capsys, github)
    assert (code, out.out) == (0, "\n")
    assert "hosts-approved" in out.err
