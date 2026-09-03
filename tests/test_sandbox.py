import subprocess
from pathlib import Path

import pytest

from angrist.sandbox import WorktreeSandbox, current_branch


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "master"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    return repo


def test_current_branch_detects_head(git_repo):
    assert current_branch(git_repo) == "master"


def test_enter_creates_worktree_and_branch(git_repo):
    with WorktreeSandbox(base_branch="master", repo_path=git_repo) as wt_path:
        assert wt_path.exists()
        assert (wt_path / "a.txt").read_text() == "hello\n"
        # worktree must live outside the repo tree
        assert git_repo not in wt_path.parents

    branches = subprocess.run(
        ["git", "branch", "--list"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout
    worktrees = subprocess.run(
        ["git", "worktree", "list"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout
    # on clean exit (no exception), worktree/branch are left in place
    assert str(wt_path) in worktrees or wt_path.as_posix() in worktrees


def test_exception_triggers_cleanup(git_repo):
    sandbox = WorktreeSandbox(base_branch="master", repo_path=git_repo)
    with pytest.raises(RuntimeError):
        with sandbox as wt_path:
            assert wt_path.exists()
            raise RuntimeError("boom")

    worktrees = subprocess.run(
        ["git", "worktree", "list"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout
    assert str(sandbox.worktree_path) not in worktrees
    assert sandbox.worktree_path.as_posix() not in worktrees
    assert not sandbox.worktree_path.exists()

    branches = subprocess.run(
        ["git", "branch", "--list"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout
    assert sandbox.branch_name not in branches


def test_main_workspace_untouched(git_repo):
    original_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    sandbox = WorktreeSandbox(base_branch="master", repo_path=git_repo)
    with pytest.raises(RuntimeError):
        with sandbox as wt_path:
            (wt_path / "a.txt").write_text("changed\n")
            raise RuntimeError("boom")

    assert (git_repo / "a.txt").read_text() == "hello\n"
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head_after == original_head
