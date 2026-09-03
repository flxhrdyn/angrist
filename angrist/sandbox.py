from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path


def current_branch(repo_path: str | Path = ".") -> str:
    """The repo's current branch. Used as the default base branch so we
    never assume 'master' or 'main'."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=Path(repo_path),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _handle_remove_readonly(func, path, exc_info):
    """Clear readonly bit on Windows files and retry deletion."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass



class WorktreeSandbox:
    """Isolates edits in a temporary git worktree + branch.

    On clean exit, the worktree/branch are left in place for the caller
    to inspect, merge, or clean up. On an exception inside the `with`
    block, the worktree and branch are force-removed so the main
    workspace is never left dirty.
    """

    def __init__(self, base_branch: str, repo_path: str | Path = "."):
        self.base_branch = base_branch
        self.repo_path = Path(repo_path)
        self.branch_name: str | None = None
        self.worktree_path: Path | None = None

    def __enter__(self) -> Path:
        suffix = uuid.uuid4().hex[:8]
        self.branch_name = f"angrist-sandbox-{suffix}"
        # Outside the repo tree on purpose: a worktree inside the repo
        # would pollute the main workspace's git status and be swept up
        # by its test/lint runs.
        self.worktree_path = Path(tempfile.gettempdir()) / f"angrist-sandbox-{suffix}"
        subprocess.run(
            [
                "git", "worktree", "add", "-b", self.branch_name,
                str(self.worktree_path), self.base_branch,
            ],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return self.worktree_path

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.cleanup()
        return False

    def cleanup(self) -> None:
        if self.worktree_path is not None:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(self.worktree_path)],
                cwd=self.repo_path,
                check=False,
                capture_output=True,
                text=True,
            )
            # N4 FIX: Ensure physical directory is completely removed on Windows
            if self.worktree_path.exists():
                shutil.rmtree(
                    self.worktree_path,
                    onerror=_handle_remove_readonly,
                    ignore_errors=True,
                )
        if self.branch_name is not None:
            subprocess.run(
                ["git", "branch", "-D", self.branch_name],
                cwd=self.repo_path,
                check=False,
                capture_output=True,
                text=True,
            )
