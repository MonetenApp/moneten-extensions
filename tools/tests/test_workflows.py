import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def jobs(name):
    text = (WORKFLOWS / name).read_text()
    return dict(re.findall(r"(?ms)^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)", text.split("\njobs:\n", 1)[1]))


def test_no_checkout_keeps_the_token():
    for path in WORKFLOWS.glob("*.yml"):
        for step in re.split(r"\n\s+- ", path.read_text()):
            if "actions/checkout@" in step:
                assert "persist-credentials: false" in step, path.name


def test_python_packages_are_installed_by_hash():
    setup = (WORKFLOWS.parent.parent / "tools" / "setup.sh").read_text()
    assert re.findall(r"pip install[^\n]*", setup) == ['pip install --quiet --require-hashes --only-binary :all: --requirement "$root/tools/requirements.txt"']
    requirements = (WORKFLOWS.parent.parent / "tools" / "requirements.txt").read_text()
    pinned = re.findall(r"(?m)^([A-Za-z0-9_.-]+)==\S+[^\n]*\\\n((?:\s+--hash=sha256:[0-9a-f]{64}[^\n]*\n)+)", requirements)
    assert {name for name, _ in pinned} >= {"jsonschema", "pytest", "referencing", "rpds-py", "attrs"}
    assert len(pinned) == len(re.findall(r"(?m)^[A-Za-z0-9_.-]+==", requirements))
    for path in WORKFLOWS.glob("*.yml"):
        assert "pip install" not in path.read_text(), path.name


def test_ext_test_is_skipped_as_a_job_while_ext_lock_pins_no_release():
    job = jobs("check.yml")["ext-test"]
    assert re.search(r"(?m)^    if: needs\.checks\.outputs\.ext-version != ''$", job)
    assert "echo \"::notice" not in job


def steps(job):
    return re.split(r"\n      - ", job)[1:]


def test_checks_reads_ext_lock_only_through_its_parser():
    found = jobs("check.yml")
    lock = next(s for s in steps(found["checks"]) if s.startswith("id: ext-lock"))
    assert 'run: python3 tools/ext_lock.py >> "$GITHUB_OUTPUT"' in lock
    assert "ext.lock" not in found["checks"].replace("tools/ext.lock", "").replace("tools/ext_lock.py", "")
    for field in ("version", "commit", "url", "sha256"):
        assert f"ext-{field}: ${{{{ steps.ext-lock.outputs.{field} }}}}" in found["checks"]
        assert f"${{{{ needs.checks.outputs.ext-{field} }}}}" in found["ext-test"]


def test_ext_test_replays_every_recording_only_with_the_checked_release():
    job = jobs("check.yml")["ext-test"]
    job_steps = steps(job)
    names = [step.split("\n")[0] for step in job_steps]
    on_main = names.index("name: Require the tag of the release on main of MonetenApp/Moneten")
    download = names.index("name: Download the pinned release of ext")
    version = names.index("name: Require the pinned version and commit")
    replay = names.index("name: Replay every recording with ext")
    assert on_main < download < version < replay
    assert "curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o .cache/ext.zip \"$URL\"" in job_steps[download]
    assert 'echo "$SHA256  .cache/ext.zip" | shasum -a 256 -c' in job_steps[download]
    assert job_steps[download].index("shasum") < job_steps[download].index("unzip")
    assert '"ext $VERSION (commit $COMMIT), API version "*' in job_steps[version]
    assert "run: python3 tools/check_package.py --ext .cache/ext/ext extensions/*/ docs/guide/tutorial" in job_steps[replay]
    assert "swift build" not in job
    assert "check-all.sh" not in job


def test_sign_off_counts_only_labels_that_a_maintainer_bound_to_the_head():
    job = jobs("sign-off.yml")["sign-off"]
    assert "trusted/tools/fresh_labels.py" in job
    assert '--labels "$FRESH_LABELS"' in job
    assert "$LABELS" not in job


def test_sign_off_runs_the_tools_of_the_base_and_reads_the_pull_request_only_as_data():
    text = (WORKFLOWS / "sign-off.yml").read_text()
    assert re.search(r"(?m)^on:\n  pull_request_target:\n    branches: \[main\]\n    types: \[opened, synchronize, reopened, labeled, unlabeled\]$", text)
    assert re.search(r"(?m)^permissions: \{\}$", text)
    assert "secrets." not in text
    job = jobs("sign-off.yml")["sign-off"]
    assert re.search(r"(?m)^    name: maintainer sign-off$", job)
    assert set(re.findall(r"(?m)^      (\w[\w-]*): (\w+)$", job.split("    permissions:\n", 1)[1].split("    steps:", 1)[0])) == {
        ("contents", "read"), ("pull-requests", "read")}
    assert "actions/cache@" not in job
    checkouts = [s for s in steps(job) if "actions/checkout@" in s]
    assert len(checkouts) == 2
    assert "ref: ${{ github.event.pull_request.base.sha }}" in checkouts[0] and "path: trusted" in checkouts[0]
    assert "ref: ${{ github.event.pull_request.head.sha }}" in checkouts[1] and "path: pull-request" in checkouts[1]
    for step in steps(job):
        for script in re.findall(r"[\w./-]+\.(?:py|sh)\b", step.partition("run:")[2]):
            assert script.startswith("trusted/tools/"), script
    assert "--root pull-request" in job


def test_only_the_sign_off_runs_on_pull_request_target():
    for path in WORKFLOWS.glob("*.yml"):
        if path.name != "sign-off.yml":
            assert "pull_request_target" not in path.read_text(), path.name
    assert "sign-off" not in jobs("check.yml")


def test_each_signing_job_holds_only_the_permissions_it_uses():
    text = (WORKFLOWS / "sign.yml").read_text()
    assert re.search(r"(?m)^permissions: \{\}$", text)
    found = jobs("sign.yml")
    granted = {name: set(re.findall(r"(?m)^      ([\w-]+): (\w+)$", job.split("    permissions:\n", 1)[1].split("\n    steps:", 1)[0].split("\n    environment:", 1)[0])) for name, job in found.items()}
    assert granted == {"check": {("contents", "read")}, "sign": {("contents", "read")}, "push": {("contents", "write")}, "deploy": {("pages", "write"), ("id-token", "write")}}
    assert "tools/check-all.sh" in found["check"]
    assert re.search(r"(?m)^    needs: check$", found["sign"])
    assert re.search(r"(?m)^      name: catalog-signing$", found["sign"])
    assert "github.token" not in found["sign"]
    assert re.search(r"(?m)^    needs: sign$", found["push"])
    assert [s.split("\n")[0] for s in steps(found["push"])] == [
        "uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
        "uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2",
        "name: Push the signed site to gh-pages",
        "uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0",
    ]
    assert "tools/push-site.sh" in steps(found["push"])[2]


def test_pages_deploys_the_tree_that_was_pushed():
    found = jobs("sign.yml")
    assert re.search(r'tools/publish.sh "\$key" "\$RUNNER_TEMP/signed"', found["sign"])
    assert "actions/upload-pages-artifact@" not in found["sign"]
    upload = next(s for s in steps(found["push"]) if "actions/upload-pages-artifact@" in s)
    assert "path: ${{ runner.temp }}/signed/site" in upload
    assert re.search(r"(?m)^    needs: push$", found["deploy"])
    assert re.search(r"(?m)^      name: github-pages$", found["deploy"])
    assert "actions/deploy-pages@" in found["deploy"]


def test_actions_are_pinned_to_a_commit():
    for path in WORKFLOWS.glob("*.yml"):
        for action in re.findall(r"uses: (\S+)", path.read_text()):
            assert re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", action), (path.name, action)


def test_ext_test_runs_only_a_release_tagged_on_main_of_the_app_repository():
    found = jobs("check.yml")
    assert "repository=" not in (WORKFLOWS.parent.parent / "tools" / "ext.lock").read_text()
    on_main = next(s for s in steps(found["ext-test"]) if s.startswith("name: Require the tag of the release on main"))
    assert "https://github.com/MonetenApp/Moneten.git" in on_main
    assert '"+refs/tags/ext-v$VERSION:refs/tags/ext-v$VERSION"' in on_main
    assert '"$tagged" != "$COMMIT"' in on_main
    assert 'merge-base --is-ancestor "$COMMIT" origin/main' in on_main
