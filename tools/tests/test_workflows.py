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


def test_ext_test_is_skipped_as_a_job_while_ext_lock_pins_no_commit():
    job = jobs("check.yml")["ext-test"]
    assert re.search(r"(?m)^    if: needs\.checks\.outputs\.ext-commit != ''$", job)
    assert "echo \"::notice" not in job


def test_sign_off_counts_only_labels_set_after_the_newest_push():
    job = jobs("check.yml")["sign-off"]
    assert "tools/fresh_labels.py" in job
    assert '--labels "$FRESH_LABELS"' in job
    assert "$LABELS" not in job


def test_no_workflow_runs_on_pull_request_target():
    for path in WORKFLOWS.glob("*.yml"):
        assert "pull_request_target" not in path.read_text(), path.name
