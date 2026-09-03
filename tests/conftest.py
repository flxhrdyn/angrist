from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from angrist.sandbox import _rmtree_force

_SANDBOX_GLOB = "angrist-sandbox-*"


@pytest.fixture(autouse=True)
def _reap_sandbox_worktrees():
    """Delete sandbox worktrees a test left in the system temp directory.

    A successful run_fix() without auto_merge deliberately keeps its worktree
    for the caller to inspect, but the caller here is a test whose repo lives
    in tmp_path, so nothing would ever remove the worktree it points at.
    """
    temp_root = Path(tempfile.gettempdir())
    before = set(temp_root.glob(_SANDBOX_GLOB))
    yield
    for path in set(temp_root.glob(_SANDBOX_GLOB)) - before:
        if path.exists():
            _rmtree_force(path)
