import json
import subprocess

import pytest

from angrist.cli import run_fix


class StubLLMClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


@pytest.fixture
def git_repo_with_bug(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "master"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)

    (repo / "mod.py").write_text(
        "def add(a, b):\n    return a - b  # bug: should be +\n"
    )
    (repo / "test_mod.py").write_text(
        "from mod import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    return repo


def test_run_fix_success_default_no_auto_merge(git_repo_with_bug):
    good_fix = "def add(a, b):\n    return a + b\n"
    client = StubLLMClient([good_fix])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the subtraction bug, should add not subtract",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest",
        lint_cmd="python -c pass",  # no-op lint to avoid ruff dependency in test
        auto_merge=False,
    )

    assert result["status"] == "success"
    assert result["branch"] is not None
    # main workspace file must be untouched (manual merge mode)
    assert "a - b" in (git_repo_with_bug / "mod.py").read_text()

    worktrees = subprocess.run(
        ["git", "worktree", "list"], cwd=git_repo_with_bug, capture_output=True, text=True, check=True
    ).stdout
    assert result["branch"] in worktrees


def test_run_fix_retries_on_scope_violation_then_succeeds(git_repo_with_bug):
    """First LLM response edits an unrelated function; guard must reject it,
    feed the violation back, and accept the clean second attempt."""
    (git_repo_with_bug / "mod.py").write_text(
        "def add(a, b):\n    return a - b\n\n\ndef other(x):\n    return x\n"
    )
    subprocess.run(["git", "add", "."], cwd=git_repo_with_bug, check=True)
    subprocess.run(["git", "commit", "-m", "add other"], cwd=git_repo_with_bug, check=True)

    # apply_patch only writes the target span, so a violation is staged by
    # returning a node whose text carries an edited copy of other() along
    # with it -- that lands inside the file and the guard sees other()
    # modified.
    violating_fix = (
        "def add(a, b):\n    return a + b\n\n\ndef other(x):\n    return x + 1\n"
    )
    good_fix = "def add(a, b):\n    return a + b\n"
    client = StubLLMClient([violating_fix, good_fix])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="python -c pass",
        lint_cmd="python -c pass",
        auto_merge=False,
    )

    assert result["status"] == "success"
    assert len(client.prompts) == 2
    # the retry prompt must carry the rejection reason back to the model
    assert "rejected" in client.prompts[1].lower()


def test_run_fix_fails_after_exhausting_retries(git_repo_with_bug):
    unusable = "I cannot help with that."
    client = StubLLMClient([unusable, unusable, unusable])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="python -c pass",
        lint_cmd="python -c pass",
        auto_merge=False,
    )

    assert result["status"] == "failed"
    assert len(client.prompts) == 3
    # main workspace untouched
    assert "a - b" in (git_repo_with_bug / "mod.py").read_text()


def test_run_fix_ignores_preexisting_test_failure(git_repo_with_bug):
    """A test that was already failing before the patch must not fail the run."""
    (git_repo_with_bug / "test_unrelated.py").write_text(
        "def test_already_broken():\n    assert False\n"
    )
    subprocess.run(["git", "add", "."], cwd=git_repo_with_bug, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add failing test"], cwd=git_repo_with_bug, check=True
    )

    client = StubLLMClient(["def add(a, b):\n    return a + b\n"])
    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest test_mod.py",
        lint_cmd="python -c pass",
        auto_merge=False,
    )

    assert result["status"] == "success"


def test_run_fix_defaults_base_branch_to_current(git_repo_with_bug):
    client = StubLLMClient(["def add(a, b):\n    return a + b\n"])
    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch=None,  # must resolve to "master" via current_branch()
        test_cmd="pytest",
        lint_cmd="python -c pass",
        auto_merge=False,
    )

    assert result["status"] == "success"


def test_run_fix_auto_merge_merges_into_base(git_repo_with_bug):
    good_fix = "def add(a, b):\n    return a + b\n"
    client = StubLLMClient([good_fix])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest",
        lint_cmd="python -c pass",
        auto_merge=True,
    )

    assert result["status"] == "success"
    assert "a + b" in (git_repo_with_bug / "mod.py").read_text()

    worktrees = subprocess.run(
        ["git", "worktree", "list"], cwd=git_repo_with_bug, capture_output=True, text=True, check=True
    ).stdout
    assert result["branch"] not in worktrees


def test_run_fix_fails_on_missing_target_without_creating_sandbox(git_repo_with_bug):
    client = StubLLMClient([])
    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="does_not_exist",
        instruction="fix it",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
    )
    assert result["status"] == "failed"
    assert "No target matching" in result["reason"]
    worktrees = subprocess.run(
        ["git", "worktree", "list"], cwd=git_repo_with_bug, capture_output=True, text=True, check=True
    ).stdout
    assert len(worktrees.strip().splitlines()) == 1


def test_run_fix_cleans_up_worktree_on_failure(git_repo_with_bug):
    """H1 verification: failing runs clean up the temporary worktree."""
    client = StubLLMClient(["def add(a, b):\n    return 'bad'\n"] * 3)
    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest",
        lint_cmd="python -c pass",
        max_retries=1,
    )
    assert result["status"] == "failed"
    worktrees = subprocess.run(
        ["git", "worktree", "list"],
        cwd=git_repo_with_bug,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # Only the main worktree should remain
    assert len(worktrees.strip().splitlines()) == 1


def test_run_fix_rejects_file_outside_repo(git_repo_with_bug, tmp_path):
    """H4 verification: file outside repository returns clean error without unhandled ValueError."""
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("def foo(): pass\n")
    client = StubLLMClient([])
    result = run_fix(
        file_path=str(outside_file),
        target="foo",
        instruction="fix it",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
    )
    assert result["status"] == "failed"
    assert "not within repository" in result["reason"]


def test_run_fix_auto_merge_fails_gracefully_when_working_tree_dirty(git_repo_with_bug):
    """N1 verification: auto_merge does not overwrite or fail if user workspace is dirty."""
    # Dirty the main workspace
    (git_repo_with_bug / "dirty.txt").write_text("uncommitted changes")

    good_fix = "def add(a, b):\n    return a + b\n"
    client = StubLLMClient([good_fix])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest",
        lint_cmd="python -c pass",
        auto_merge=True,
    )
    assert result["status"] == "failed"
    assert "uncommitted changes" in result["reason"]
    # Branch is preserved for the user
    assert result["branch"] is not None


def test_run_fix_delta_gate_detects_new_failure_among_preexisting(git_repo_with_bug):
    """H3 verification: delta gate detects newly introduced test failure even if baseline had a failing test."""
    # Add an unrelated pre-existing failing test AND a passing test
    (git_repo_with_bug / "test_other.py").write_text(
        "def test_already_failing():\n    assert False\n\n"
        "def test_currently_passing():\n    from mod import add\n    assert add(1, 1) != 'broken'\n"
    )
    subprocess.run(["git", "add", "."], cwd=git_repo_with_bug, check=True)
    subprocess.run(["git", "commit", "-m", "add baseline tests"], cwd=git_repo_with_bug, check=True)

    # Patch that fixes `add` in a way that breaks `test_currently_passing`
    bad_fix = "def add(a, b):\n    return 'broken'\n"
    client = StubLLMClient([bad_fix])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest test_other.py",
        lint_cmd="python -c pass",
        max_retries=1,
    )
    assert result["status"] == "failed"
    assert "tests regressed" in result["reason"]


def test_run_fix_test_gate_catches_error_conversion(git_repo_with_bug):
    """N5 verification: turning a FAILED test into an ERROR (ImportError/CollectionError) is caught."""
    # Baseline has FAILED
    (git_repo_with_bug / "test_mod.py").write_text("from mod import add\ndef test_it(): assert add(1, 1) == 999\n")
    subprocess.run(["git", "add", "."], cwd=git_repo_with_bug, check=True)
    subprocess.run(["git", "commit", "-m", "add failing test"], cwd=git_repo_with_bug, check=True)

    # Patch introduces an import error inside the function body so sanitizer passes,
    # but running the test produces ERROR / test runner failure
    broken_fix = "def add(a, b):\n    import nonexistent_module_causes_error\n    return a + b\n"
    client = StubLLMClient([broken_fix])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest",
        lint_cmd="python -c pass",
        max_retries=1,
    )
    assert result["status"] == "failed"
    assert "test runner failed" in result["reason"] or "test/error(s) appeared" in result["reason"] or "still failing" in result["reason"]



def test_run_fix_lint_gate_catches_different_rule_with_equal_count():
    """N6 verification: lint gate compares rule signatures, not just line counts."""
    import subprocess

    from angrist.cli import _check_lint_regression

    base = subprocess.CompletedProcess(
        args=["ruff"], returncode=1, stdout="a.py:1:1: F401 'unused' imported but unused\n"
    )
    # Candidate replaces F401 with E711 (count is still 1, but rule is different)
    cand = subprocess.CompletedProcess(
        args=["ruff"], returncode=1, stdout="a.py:9:9: E711 comparison to None should be 'if cond is None:'\n"
    )
    res = _check_lint_regression(base, cand)
    assert res is not None
    assert "new finding(s) introduced" in res


def test_run_fix_aborts_early_on_invalid_baseline_command(git_repo_with_bug):
    """H2 verification: invalid baseline test command aborts before invoking LLM."""
    client = StubLLMClient([])  # Client should not even be called
    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="python -c 'import sys; sys.exit(4)'",  # Exit code 4 = usage error
        lint_cmd="python -c pass",
    )
    assert result["status"] == "failed"
    assert "Baseline test command failed with exit code 4" in result["reason"]


def test_run_fix_aborts_early_on_invalid_baseline_lint_command(git_repo_with_bug):
    """N8 verification: invalid baseline lint command aborts before invoking LLM."""
    client = StubLLMClient([])
    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="pytest",
        lint_cmd="python -c 'import sys; sys.exit(2)'",  # Exit code 2 = crash/fatal
    )
    assert result["status"] == "failed"
    assert "Baseline lint command failed with exit code 2" in result["reason"]


def test_run_fix_test_gate_reports_exact_remaining_failures_on_partial_fix(git_repo_with_bug):
    """N9 verification: partial fix reports remaining failing tests accurately."""
    import subprocess

    from angrist.cli import _check_test_regression

    # Baseline had two failing tests
    base = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=1,
        stdout="FAILED tests/t.py::test_a - fail\nFAILED tests/t.py::test_b - fail\n",
    )
    # Candidate fixed test_b, but test_a still fails
    cand = subprocess.CompletedProcess(
        args=["pytest"],
        returncode=1,
        stdout="FAILED tests/t.py::test_a - fail\n",
    )
    res = _check_test_regression(base, cand)
    assert res is not None
    assert "tests still failing after the patch (1 test(s) failed): tests/t.py::test_a" in res
    assert "test runner failed" not in res







def _lint_result(returncode, stdout="", stderr=""):
    result = subprocess.CompletedProcess(args=["ruff"], returncode=returncode)
    result.stdout = stdout
    result.stderr = stderr
    return result


def _ruff_json(*findings):
    payload = [
        {"filename": filename, "code": code, "name": "x", "message": "m"}
        for filename, code in findings
    ]
    return json.dumps(payload)


def test_lint_gate_catches_new_finding_of_an_already_present_rule():
    """A second F841 in a file that already had one is still a regression."""
    from angrist.cli import _check_lint_regression

    base = _lint_result(1, _ruff_json(("m.py", "F841")))
    cand = _lint_result(1, _ruff_json(("m.py", "F841"), ("m.py", "F841")))

    res = _check_lint_regression(base, cand)
    assert res is not None
    assert "F841" in res


def test_lint_gate_ignores_line_shifts_of_unchanged_findings():
    """Identical findings must compare equal regardless of position."""
    from angrist.cli import _check_lint_regression

    base = _lint_result(1, _ruff_json(("m.py", "F841")))
    cand = _lint_result(1, _ruff_json(("m.py", "F841")))

    assert _check_lint_regression(base, cand) is None


def test_lint_gate_reports_unrecognized_output_instead_of_passing():
    """Unparseable lint output must not be mistaken for a clean report."""
    from angrist.cli import _check_lint_regression

    base = _lint_result(1, "F841 Local variable is unused\n  |\n5 |     x = 1\n")
    cand = _lint_result(1, "F841 Local variable is unused\n  |\n6 |     x = 1\n")

    res = _check_lint_regression(base, cand)
    assert res is not None
    assert "unrecognized format" in res


def test_lint_input_error_detects_in_band_io_failure():
    """Ruff reports an unreadable path as an E902 finding, not on stderr."""
    from angrist.cli import lint_input_error

    payload = json.dumps(
        [{"filename": "gone.py", "code": "E902", "name": "io-error", "message": "missing"}]
    )
    assert "E902" in lint_input_error(_lint_result(1, payload))


def test_lint_input_error_detects_empty_report_beside_stderr_error():
    """A rule filter can suppress E902, leaving an empty report plus a warning."""
    from angrist.cli import lint_input_error

    result = _lint_result(0, "[]", "warning: Failed to lint gone.py: (os error 3)")
    assert lint_input_error(result) is not None


def test_lint_input_error_passes_a_healthy_run():
    from angrist.cli import lint_input_error

    assert lint_input_error(_lint_result(1, _ruff_json(("m.py", "F401")))) is None
    assert lint_input_error(_lint_result(0, "[]")) is None
