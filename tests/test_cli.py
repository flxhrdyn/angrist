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

