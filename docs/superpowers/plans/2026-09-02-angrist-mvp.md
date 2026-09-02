# angrist MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `angrist`, a headless Python CLI that fixes a single Python
function/class through git-worktree isolation and AST-scope-locked LLM
patching, targeting free/local OpenAI-compatible models.

**Architecture:** Four focused modules (`sandbox.py`, `ast_guard.py`,
`patcher.py`, `cli.py`) wired by a `Typer` CLI. `sandbox.py` isolates all
edits in a temporary `git worktree`. `ast_guard.py` resolves a qualified
target (`file::function_name` or `file::ClassName.method_name`) via
`py-tree-sitter`, extracts only that node's source, and validates any
candidate replacement file against a strict whitelist (target node +
imports + non-colliding new top-level nodes; everything else must be
byte-identical AST). `patcher.py` talks to any OpenAI-compatible endpoint
through a tiny `LLMClient` protocol. `cli.py` wires scope -> sandbox ->
patch/guard retry loop (max 3) -> lint -> test -> report/merge.

**Tech Stack:** Python 3.11+, Typer, Rich, py-tree-sitter,
tree-sitter-python, `subprocess` (native `git worktree`), `httpx` (or
`requests`) for the OpenAI-compatible HTTP call, pytest for the test
suite.

**Spec:** `docs/superpowers/specs/2026-09-02-angrist-design.md`

## Global Constraints

- Language support: Python only (spec "Scope (MVP)").
- Target addressing: `file::function_name` or `file::ClassName.method_name`
  qualifier only — no bare-name lookup (spec "ast_guard.py").
- Patch strategy: full-node-replace only, no unified-diff patching (spec
  "Scope (MVP)").
- LLM access: via `LLMClient` protocol over OpenAI-compatible HTTP API,
  no LiteLLM dependency; default provider Groq, default model `gpt-oss`
  (spec "Scope (MVP)").
- Guard whitelist: target node, imports, and net-new top-level nodes
  (name must not collide with an existing top-level name) may differ;
  every other existing node must be byte-identical AST (spec
  "ast_guard.py").
- Retry policy: on `ASTScopeViolationError`, retry with violation detail
  fed back into the next prompt, max 3 attempts total, then rollback
  (spec "Error Handling").
- Validation gate: `--lint-cmd` (default `ruff check`) then `--test-cmd`
  (default `pytest`) must both pass inside the sandbox before success
  (spec "cli.py").
- Merge: default leaves sandbox branch + diff summary for manual review;
  `--auto-merge` merges and cleans up automatically (spec "cli.py").
- Sandbox safety: main workspace must never be touched; any unhandled
  exception inside the sandbox context force-removes the worktree/branch
  (spec "sandbox.py").
- Sandbox location: worktree is created in the system temp dir, never
  inside the repo tree (spec "sandbox.py").
- Base branch: defaults to the repo's current branch via
  `git rev-parse --abbrev-ref HEAD`, never a hardcoded name (spec
  "sandbox.py").
- Guard granularity: for a `ClassName.method_name` target, only that
  method node is whitelisted — sibling methods and class attributes must
  be byte-identical (spec "ast_guard.py").
- Comparison baseline: the pre-patch source comes from
  `git show <base-branch>:<path>` or memory — never a scratch file
  written inside the worktree (spec "ast_guard.py").
- Output sanitization: fence-stripping, indentation normalization to the
  target's original column, and a parse check are mechanical steps in
  `patcher.py`, not prompt instructions; failure is retried like a scope
  violation (spec "patcher.py").
- Validation gate is a delta vs a pre-patch baseline run, not an
  absolute exit code (spec "cli.py").

---

## File Structure

```
angrist/
  angrist/
    __init__.py
    sandbox.py       # WorktreeSandbox context manager
    ast_guard.py      # target resolution, node extraction, scope validation
    patcher.py        # LLMClient protocol + OpenAI-compatible impl + patch apply
    cli.py             # Typer wiring: scope -> sandbox -> patch/guard -> lint/test -> merge
  tests/
    test_sandbox.py
    test_ast_guard.py
    test_patcher.py
    test_cli.py
    fixtures/
      sample_module.py   # fixture Python file used by ast_guard + cli tests
  pyproject.toml
```

- `sandbox.py`: git worktree lifecycle only. No AST/LLM knowledge.
- `ast_guard.py`: parsing, target resolution, extraction, whitelist
  validation. No git/LLM knowledge.
- `patcher.py`: LLM I/O + writing candidate text into a file. No git/AST
  validation logic (calls into `ast_guard` for validation).
- `cli.py`: orchestration only, no business logic duplicated from the
  other three modules.

---

### Task 0 (optional, recommended before Task 1): Model-quality spike

The spec's "Key Risk" section: nothing yet proves a free-tier or local
open-weight model can produce correct, in-scope replacements often
enough for the tool to feel usable. This task is **throwaway** — its
output is a measurement, not code that ships.

Requires `ANGRIST_LLM_API_KEY` set for the chosen provider.

- [ ] **Step 1: Collect 10 broken functions**

Pick 10 real single-function bugs (off-by-one, wrong operator, missing
guard, bad default) from any Python repo. For each, note the file, the
qualifier, and the correct fix.

- [ ] **Step 2: Write a throwaway probe script**

`scratch/spike_probe.py` (not committed to the package):

```python
import os

import httpx

PROMPT = """Return ONLY the complete replacement source for this Python
function (no explanations, no markdown fences).

Instruction: {instruction}

Current source:
{source}
"""


def ask(source: str, instruction: str) -> str:
    response = httpx.post(
        os.environ.get("ANGRIST_LLM_BASE_URL", "https://api.groq.com/openai/v1")
        + "/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['ANGRIST_LLM_API_KEY']}"},
        json={
            "model": os.environ.get("ANGRIST_LLM_MODEL", "gpt-oss"),
            "messages": [
                {"role": "user", "content": PROMPT.format(source=source, instruction=instruction)}
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    # feed each of the 10 cases through ask() and print the raw output
    ...
```

- [ ] **Step 3: Score the 10 outputs by hand**

Record three rates:
- **fence/format rate**: how often output arrives wrapped in markdown
  fences or with prose around it (tells you how load-bearing
  `sanitize_output` is).
- **scope-violation rate**: how often output includes nodes other than
  the target.
- **correctness rate**: how often the fix is actually right.

- [ ] **Step 4: Decide**

- Correctness above ~50% and violations mostly format-level -> proceed
  to Task 1 as planned.
- Correctness very low -> the guard design still holds, but record in
  the spec that the default model needs to change (a larger free-tier
  model, or a local model) before the CLI is worth polishing.
- Note the findings in the spec's "Key Risk" section either way.

- [ ] **Step 5: Delete the probe script**

It is throwaway. `rm -rf scratch/`.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `angrist/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: installable package `angrist`, `pytest` runnable from repo
  root.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "angrist"
version = "0.1.0"
description = "Git-worktree isolated, AST-scope-locked micro-agent for precise single-function code fixes"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "rich>=13.0",
    "tree-sitter>=0.21",
    "tree-sitter-python>=0.21",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.5"]

[project.scripts]
angrist = "angrist.cli:app"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["angrist*"]
```

- [ ] **Step 2: Create empty package/test init files**

`angrist/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

- [ ] **Step 3: Install package in editable mode with dev deps**

Run: `pip install -e ".[dev]"`
Expected: install succeeds, `angrist` importable.

- [ ] **Step 4: Verify pytest collects (no tests yet)**

Run: `pytest`
Expected: `no tests ran` (exit code 5) — confirms pytest wired to repo
root, no import errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml angrist/__init__.py tests/__init__.py
git commit -m "chore: scaffold angrist package"
```

---

### Task 2: `WorktreeSandbox`

**Files:**
- Create: `angrist/sandbox.py`
- Test: `tests/test_sandbox.py`

**Interfaces:**
- Produces:
  - `current_branch(repo_path: str | Path) -> str` — returns the repo's
    current branch via `git rev-parse --abbrev-ref HEAD`. Used as the
    default `base_branch` everywhere instead of a hardcoded name.
  - `class WorktreeSandbox` — constructor
    `WorktreeSandbox(base_branch: str, repo_path: str | Path = ".")`.
    The worktree directory is created under the system temp dir, NOT
    inside `repo_path`.
  - `WorktreeSandbox.__enter__() -> Path` — returns path to the new
    worktree directory.
  - `WorktreeSandbox.__exit__(exc_type, exc_val, exc_tb) -> bool` —
    cleans up (force-removes worktree + deletes temp branch) if
    `exc_type is not None`; returns `False` (does not suppress
    exceptions).
  - `WorktreeSandbox.branch_name: str` — the temp branch name, set in
    `__enter__`.
  - `WorktreeSandbox.worktree_path: Path` — set in `__enter__`.

- [ ] **Step 1: Write failing test for successful enter/exit (no error)**

```python
# tests/test_sandbox.py
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
    assert str(wt_path) in worktrees
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sandbox.py::test_enter_creates_worktree_and_branch -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'angrist.sandbox'`

- [ ] **Step 3: Implement `WorktreeSandbox` enter/exit**

```python
# angrist/sandbox.py
from __future__ import annotations

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
        if self.branch_name is not None:
            subprocess.run(
                ["git", "branch", "-D", self.branch_name],
                cwd=self.repo_path,
                check=False,
                capture_output=True,
                text=True,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sandbox.py::test_enter_creates_worktree_and_branch -v`
Expected: PASS

- [ ] **Step 5: Write failing test for exception-triggered cleanup**

```python
# tests/test_sandbox.py (append)
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
```

- [ ] **Step 6: Run tests to verify they fail correctly, then pass after review**

Run: `pytest tests/test_sandbox.py -v`
Expected: all pass (implementation from Step 3 already satisfies these;
if any fails, fix `cleanup()` until all three pass).

- [ ] **Step 7: Commit**

```bash
git add angrist/sandbox.py tests/test_sandbox.py
git commit -m "feat: add WorktreeSandbox for isolated git worktree edits"
```

---

### Task 3: AST target resolution and extraction

**Files:**
- Create: `angrist/ast_guard.py`
- Create: `tests/fixtures/sample_module.py`
- Test: `tests/test_ast_guard.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class TargetNotFoundError(Exception)`
  - `class AmbiguousTargetError(Exception)`
  - `parse_target(qualifier: str) -> tuple[str | None, str]` — splits
    `"ClassName.method_name"` into `("ClassName", "method_name")` or
    `"function_name"` into `(None, "function_name")`.
  - `extract_node_source(file_path: str | Path, qualifier: str) -> str`
    — returns exact source text of the addressed function/method node.
    Raises `TargetNotFoundError` if no match, `AmbiguousTargetError` if
    more than one match for the given qualifier.

- [ ] **Step 1: Create fixture file**

```python
# tests/fixtures/sample_module.py
import os


def top_level_func(x):
    return x + 1


class Foo:
    def method_a(self, x):
        return x * 2

    def method_a_dup_helper(self):
        pass


class Bar:
    def method_a(self, x):
        return x * 3
```

- [ ] **Step 2: Write failing tests for `parse_target` and extraction**

```python
# tests/test_ast_guard.py
from pathlib import Path

import pytest

from angrist.ast_guard import (
    AmbiguousTargetError,
    TargetNotFoundError,
    extract_node_source,
    parse_target,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_module.py"


def test_parse_target_function_only():
    assert parse_target("top_level_func") == (None, "top_level_func")


def test_parse_target_class_method():
    assert parse_target("Foo.method_a") == ("Foo", "method_a")


def test_extract_top_level_function():
    src = extract_node_source(FIXTURE, "top_level_func")
    assert "def top_level_func(x):" in src
    assert "return x + 1" in src


def test_extract_class_method_disambiguates_duplicate_names():
    src_foo = extract_node_source(FIXTURE, "Foo.method_a")
    assert "return x * 2" in src_foo

    src_bar = extract_node_source(FIXTURE, "Bar.method_a")
    assert "return x * 3" in src_bar


def test_extract_missing_target_raises():
    with pytest.raises(TargetNotFoundError):
        extract_node_source(FIXTURE, "does_not_exist")


def test_extract_missing_class_raises():
    with pytest.raises(TargetNotFoundError):
        extract_node_source(FIXTURE, "NoSuchClass.method_a")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_ast_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'angrist.ast_guard'`

- [ ] **Step 4: Implement `parse_target` and `extract_node_source`**

```python
# angrist/ast_guard.py
from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())


class TargetNotFoundError(Exception):
    pass


class AmbiguousTargetError(Exception):
    pass


class ASTScopeViolationError(Exception):
    pass


def _make_parser() -> Parser:
    return Parser(PY_LANGUAGE)


def parse_target(qualifier: str) -> tuple[str | None, str]:
    if "." in qualifier:
        class_name, func_name = qualifier.split(".", 1)
        return class_name, func_name
    return None, qualifier


def _iter_function_defs(tree_root, class_name: str | None):
    """Yield (node, enclosing_class_name_or_None) for every function_definition
    node in the tree, scoped to a class body if class_name is given."""
    if class_name is None:
        for node in tree_root.children:
            if node.type == "function_definition":
                yield node, None
        return

    for node in tree_root.children:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.text.decode() == class_name:
                body = node.child_by_field_name("body")
                if body is not None:
                    for child in body.children:
                        if child.type == "function_definition":
                            yield child, class_name


def extract_node_source(file_path: str | Path, qualifier: str) -> str:
    class_name, func_name = parse_target(qualifier)
    source = Path(file_path).read_bytes()
    parser = _make_parser()
    tree = parser.parse(source)

    matches = []
    for node, _ in _iter_function_defs(tree.root_node, class_name):
        name_node = node.child_by_field_name("name")
        if name_node is not None and name_node.text.decode() == func_name:
            matches.append(node)

    if not matches:
        raise TargetNotFoundError(
            f"No target matching '{qualifier}' found in {file_path}"
        )
    if len(matches) > 1:
        raise AmbiguousTargetError(
            f"Qualifier '{qualifier}' matches {len(matches)} nodes in "
            f"{file_path}; refine the qualifier"
        )

    node = matches[0]
    return source[node.start_byte:node.end_byte].decode()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ast_guard.py -v`
Expected: PASS for all 6 tests

- [ ] **Step 6: Commit**

```bash
git add angrist/ast_guard.py tests/fixtures/sample_module.py tests/test_ast_guard.py
git commit -m "feat: add AST target resolution and node extraction"
```

---

### Task 4: AST scope whitelist validation

**Files:**
- Modify: `angrist/ast_guard.py` (add validation function)
- Test: `tests/test_ast_guard.py` (append)

**Interfaces:**
- Consumes: `parse_target`, `_iter_function_defs`, `PY_LANGUAGE` from
  Task 3 (same module, internal use).
- Produces:
  - `validate_scope_source(original_source: str, candidate_source: str, qualifier: str) -> None`
    — the real implementation, operating on source strings so the
    caller can supply the original from `git show` rather than a file
    on disk.
  - `validate_scope(original_path: str | Path, candidate_path: str | Path, qualifier: str) -> None`
    — thin file-reading wrapper around `validate_scope_source`, kept
    for tests and direct use.

  Both raise `ASTScopeViolationError` with a descriptive message if the
  candidate violates the whitelist; return `None` on success. The
  message must name the offending node (name + type) so callers can
  feed it back into a retry prompt.

  **Granularity requirement:** for a `ClassName.method_name` target,
  only that method may differ. Sibling methods and class attributes in
  the same class must be byte-identical — the enclosing
  `class_definition` is descended into, never whitelisted wholesale.

- [ ] **Step 1: Write failing tests for validation**

```python
# tests/test_ast_guard.py (append)
from angrist.ast_guard import ASTScopeViolationError, validate_scope


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return p


def test_validate_scope_allows_target_change_only(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "def foo(x):\n    return x + 1\n\n\ndef bar(x):\n    return x - 1\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return x + 100\n\n\ndef bar(x):\n    return x - 1\n",
    )
    validate_scope(original, candidate, "foo")  # should not raise


def test_validate_scope_allows_import_change(tmp_path):
    original = _write(tmp_path, "orig.py", "import os\n\n\ndef foo(x):\n    return x\n")
    candidate = _write(tmp_path, "cand.py", "import os\nimport sys\n\n\ndef foo(x):\n    return x\n")
    validate_scope(original, candidate, "foo")  # should not raise


def test_validate_scope_allows_new_noncolliding_top_level(tmp_path):
    original = _write(tmp_path, "orig.py", "def foo(x):\n    return x\n")
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return helper(x)\n\n\ndef helper(x):\n    return x + 1\n",
    )
    validate_scope(original, candidate, "foo")  # should not raise


def test_validate_scope_rejects_new_top_level_name_collision(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x\n\n\ndef bar(y):\n    return y\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "foo")


def test_validate_scope_rejects_unrelated_node_edit(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x - 1\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x - 999\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "foo")


def test_validate_scope_allows_target_method_change(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "class Foo:\n"
        "    def a(self):\n        return 1\n\n"
        "    def b(self):\n        return 2\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "class Foo:\n"
        "    def a(self):\n        return 100\n\n"
        "    def b(self):\n        return 2\n",
    )
    validate_scope(original, candidate, "Foo.a")  # should not raise


def test_validate_scope_rejects_sibling_method_edit(tmp_path):
    """The critical case: targeting Foo.a must NOT license edits to Foo.b."""
    original = _write(
        tmp_path, "orig.py",
        "class Foo:\n"
        "    def a(self):\n        return 1\n\n"
        "    def b(self):\n        return 2\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "class Foo:\n"
        "    def a(self):\n        return 100\n\n"
        "    def b(self):\n        return 999\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "Foo.a")


def test_validate_scope_rejects_class_attribute_edit(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "class Foo:\n"
        "    LIMIT = 10\n\n"
        "    def a(self):\n        return 1\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "class Foo:\n"
        "    LIMIT = 999\n\n"
        "    def a(self):\n        return 1\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "Foo.a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ast_guard.py -v -k validate_scope`
Expected: FAIL with `ImportError: cannot import name 'validate_scope'`

- [ ] **Step 3: Implement `validate_scope_source` and `validate_scope`**

The design here is a *signature map*: every node that must survive the
patch untouched is reduced to a stable identity plus its exact source
bytes. For a class-method target the map descends into the class body,
so sibling methods and class attributes are protected individually —
targeting `Foo.a` never licenses an edit to `Foo.b`.

```python
# angrist/ast_guard.py (append)

_IMPORT_TYPES = {"import_statement", "import_from_statement"}


def _node_name(node) -> str | None:
    name_node = node.child_by_field_name("name")
    return name_node.text.decode() if name_node is not None else None


def _protected_map(source: bytes, root, class_name: str | None, func_name: str):
    """Map every node that must stay byte-identical to its source bytes.

    Key is a path-like identity, e.g. ("function_definition", "bar") for a
    top-level function or ("Foo", "function_definition", "b") for a method
    inside class Foo. Imports and the target node itself are excluded --
    those are the only things allowed to change.
    """
    protected: dict[tuple, bytes] = {}

    for node in root.children:
        if node.type in _IMPORT_TYPES:
            continue

        name = _node_name(node)

        # top-level function target -> excluded from protection
        if class_name is None and node.type == "function_definition" and name == func_name:
            continue

        if node.type == "class_definition" and name == class_name:
            # Descend: protect everything in this class EXCEPT the target
            # method. This is the whole point -- the class is not a
            # blanket whitelist.
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    child_name = _node_name(child)
                    if child.type == "function_definition" and child_name == func_name:
                        continue  # the target method, allowed to change
                    key = (class_name, child.type, child_name, child.start_byte
                           if child_name is None else None)
                    protected[key] = source[child.start_byte:child.end_byte]
            # also protect the class's own header (name, bases, decorators)
            header_end = body.start_byte if body is not None else node.end_byte
            protected[(class_name, "__class_header__", None, None)] = (
                source[node.start_byte:header_end]
            )
            continue

        key = (node.type, name, None, node.start_byte if name is None else None)
        protected[key] = source[node.start_byte:node.end_byte]

    return protected


def _top_level_names(root) -> set[str]:
    names = set()
    for node in root.children:
        name = _node_name(node)
        if name is not None:
            names.add(name)
    return names


def validate_scope_source(
    original_source: str, candidate_source: str, qualifier: str
) -> None:
    class_name, func_name = parse_target(qualifier)
    orig_bytes = original_source.encode()
    cand_bytes = candidate_source.encode()

    parser = _make_parser()
    orig_root = parser.parse(orig_bytes).root_node
    cand_root = parser.parse(cand_bytes).root_node

    orig_protected = _protected_map(orig_bytes, orig_root, class_name, func_name)
    cand_protected = _protected_map(cand_bytes, cand_root, class_name, func_name)

    orig_names = _top_level_names(orig_root)

    # Every protected original node must survive byte-identical.
    for key, orig_node_bytes in orig_protected.items():
        if key not in cand_protected:
            raise ASTScopeViolationError(
                f"Node {key[:3]} present in the original is missing or "
                f"restructured in your output. Only '{qualifier}' may change."
            )
        if cand_protected[key] != orig_node_bytes:
            raise ASTScopeViolationError(
                f"Node {key[:3]} was modified, but the only node you may "
                f"change is '{qualifier}'."
            )

    # Anything extra in the candidate must be a net-new, non-colliding
    # TOP-LEVEL node. New members inside the target's class are not allowed.
    for key in cand_protected:
        if key in orig_protected:
            continue
        owner, node_type, name = key[0], key[1], key[2]
        if class_name is not None and owner == class_name:
            raise ASTScopeViolationError(
                f"You added '{name}' inside class {class_name}. New members "
                f"may only be added at top level, not inside the target class."
            )
        if name is None:
            raise ASTScopeViolationError(
                f"Unexpected new unnamed {node_type} node at top level."
            )
        if name in orig_names:
            raise ASTScopeViolationError(
                f"New top-level '{name}' collides with an existing name."
            )


def validate_scope(
    original_path: str | Path, candidate_path: str | Path, qualifier: str
) -> None:
    validate_scope_source(
        Path(original_path).read_text(),
        Path(candidate_path).read_text(),
        qualifier,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ast_guard.py -v`
Expected: PASS for all tests in the file (14 total from Tasks 3 + 4).
`test_validate_scope_rejects_sibling_method_edit` is the important one —
if it passes, the class-granularity hole is closed.

- [ ] **Step 5: Commit**

```bash
git add angrist/ast_guard.py tests/test_ast_guard.py
git commit -m "feat: add AST scope whitelist validation"
```

---

### Task 5: `LLMClient` protocol and OpenAI-compatible implementation

**Files:**
- Create: `angrist/patcher.py`
- Test: `tests/test_patcher.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone LLM I/O module).
- Produces:
  - `class LLMClient(Protocol)` with method
    `complete(self, prompt: str) -> str`.
  - `class OpenAICompatibleClient` implementing `LLMClient`:
    constructor `OpenAICompatibleClient(base_url: str, api_key: str, model: str, http_client: httpx.Client | None = None)`;
    `complete(self, prompt: str) -> str` posts to
    `f"{base_url}/chat/completions"` and returns
    `response.json()["choices"][0]["message"]["content"]`.
  - `build_patch_prompt(target_source: str, instruction: str, violation_detail: str | None = None) -> str`
    — later tasks (Task 6, CLI) call this to build the prompt sent to
    `LLMClient.complete`.

- [ ] **Step 1: Write failing test for `OpenAICompatibleClient` using a stub transport**

```python
# tests/test_patcher.py
import httpx

from angrist.patcher import OpenAICompatibleClient, build_patch_prompt


def _stub_client(expected_body_check=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if expected_body_check is not None:
            expected_body_check(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "def foo():\n    return 42\n"}}]},
        )

    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_complete_returns_message_content():
    http_client = _stub_client()
    client = OpenAICompatibleClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        model="gpt-oss",
        http_client=http_client,
    )
    result = client.complete("fix this function")
    assert result == "def foo():\n    return 42\n"


def test_complete_sends_model_and_auth_header():
    seen = {}

    def check(request: httpx.Request):
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)

    http_client = _stub_client(expected_body_check=check)
    client = OpenAICompatibleClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        model="gpt-oss",
        http_client=http_client,
    )
    client.complete("fix this function")
    assert seen["auth"] == "Bearer test-key"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"


def test_build_patch_prompt_includes_instruction_and_source():
    prompt = build_patch_prompt("def foo():\n    pass\n", "make it return 1")
    assert "def foo():" in prompt
    assert "make it return 1" in prompt


def test_build_patch_prompt_includes_violation_detail_when_present():
    prompt = build_patch_prompt(
        "def foo():\n    pass\n", "make it return 1", violation_detail="you touched bar()"
    )
    assert "you touched bar()" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_patcher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'angrist.patcher'`

- [ ] **Step 3: Implement `patcher.py`**

```python
# angrist/patcher.py
from __future__ import annotations

from typing import Protocol

import httpx


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class OpenAICompatibleClient:
    """Talks to any OpenAI-compatible /chat/completions endpoint.

    Works unmodified against Groq, local Ollama/vLLM OpenAI-compat
    servers, or the real OpenAI API — only base_url/api_key/model
    change.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._http = http_client or httpx.Client()

    def complete(self, prompt: str) -> str:
        response = self._http.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def build_patch_prompt(
    target_source: str, instruction: str, violation_detail: str | None = None
) -> str:
    parts = [
        "You are given the exact source of a single Python function or "
        "class. Return ONLY the complete replacement source for this "
        "node (no explanations, no markdown fences).",
        f"Instruction: {instruction}",
        "Current source:",
        target_source,
    ]
    if violation_detail is not None:
        parts.insert(
            1,
            f"Your previous attempt was rejected: {violation_detail}. "
            "You must only change this node's own body; do not touch "
            "anything else.",
        )
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_patcher.py -v`
Expected: PASS for all 4 tests

- [ ] **Step 5: Commit**

```bash
git add angrist/patcher.py tests/test_patcher.py
git commit -m "feat: add LLMClient protocol and OpenAI-compatible client"
```

---

### Task 6: Output sanitization and patch application

**Files:**
- Modify: `angrist/patcher.py` (add `SanitizationError`, `sanitize_output`, `apply_patch`)
- Test: `tests/test_patcher.py` (append)

**Interfaces:**
- Consumes: `_make_parser`, `parse_target`, `_iter_function_defs` from
  Task 3 (`angrist.ast_guard`).
- Produces:
  - `class SanitizationError(Exception)` — raised when model output
    cannot be turned into a single valid function/class node. Callers
    treat it exactly like `ASTScopeViolationError`: feed the message
    back, retry.
  - `sanitize_output(raw: str, target_indent: int) -> str` — strips
    markdown fences (with or without a language tag), re-indents the
    block to `target_indent` columns, and verifies the result parses as
    exactly one `function_definition` or `class_definition`. Raises
    `SanitizationError` otherwise. This is mechanical, not
    prompt-dependent: open-weight models emit fences regardless of
    instructions, so the guarantee has to live in code.
  - `apply_patch(file_path: str | Path, qualifier: str, new_node_source: str) -> None`
    — replaces the addressed node's exact source span in `file_path`
    with `new_node_source`, writing the file in place. Raises
    `angrist.ast_guard.TargetNotFoundError` /
    `AmbiguousTargetError` under the same conditions as
    `extract_node_source` (reuses the same resolution logic).
  - `target_indent(file_path: str | Path, qualifier: str) -> int` —
    the column at which the target node currently starts, so
    `sanitize_output` can normalize the model's indentation to match.

- [ ] **Step 1: Write failing tests for `sanitize_output` and `apply_patch`**

```python
# tests/test_patcher.py (append)
from pathlib import Path

import pytest

from angrist.patcher import (
    SanitizationError,
    apply_patch,
    sanitize_output,
    target_indent,
)


def test_sanitize_strips_plain_fences():
    raw = "```\ndef foo(x):\n    return x\n```"
    assert sanitize_output(raw, 0) == "def foo(x):\n    return x\n"


def test_sanitize_strips_fences_with_language_tag():
    raw = "```python\ndef foo(x):\n    return x\n```"
    assert sanitize_output(raw, 0) == "def foo(x):\n    return x\n"


def test_sanitize_reindents_method_to_target_column():
    raw = "def method_a(self, x):\n    return x * 5\n"
    result = sanitize_output(raw, 4)
    assert result == "    def method_a(self, x):\n        return x * 5\n"


def test_sanitize_dedents_overindented_output():
    raw = "        def foo(x):\n            return x\n"
    assert sanitize_output(raw, 0) == "def foo(x):\n    return x\n"


def test_sanitize_rejects_unparseable_output():
    with pytest.raises(SanitizationError):
        sanitize_output("this is not python at all !!!", 0)


def test_sanitize_rejects_prose_wrapped_output():
    raw = "Sure! Here is the fix:\n\ndef foo(x):\n    return x\n"
    with pytest.raises(SanitizationError):
        sanitize_output(raw, 0)


def test_sanitize_rejects_multiple_definitions():
    raw = "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x\n"
    with pytest.raises(SanitizationError):
        sanitize_output(raw, 0)


def test_target_indent_top_level_is_zero(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def foo(x):\n    return x\n")
    assert target_indent(f, "foo") == 0


def test_target_indent_method_is_four(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("class Foo:\n    def a(self):\n        return 1\n")
    assert target_indent(f, "Foo.a") == 4


def test_apply_patch_replaces_target_node_only(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x - 1\n"
    )
    apply_patch(target, "foo", "def foo(x):\n    return x + 999\n")

    content = target.read_text()
    assert "return x + 999" in content
    assert "def bar(x):\n    return x - 1" in content


def test_apply_patch_on_class_method(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "class Foo:\n    def method_a(self, x):\n        return x * 2\n"
    )
    apply_patch(
        target, "Foo.method_a", "    def method_a(self, x):\n        return x * 5\n"
    )

    content = target.read_text()
    assert "return x * 5" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_patcher.py -v -k "sanitize or apply_patch or target_indent"`
Expected: FAIL with `ImportError: cannot import name 'sanitize_output'`

- [ ] **Step 3: Implement `sanitize_output`, `target_indent`, `apply_patch`**

```python
# angrist/patcher.py (append)
import textwrap
from pathlib import Path

from angrist.ast_guard import _iter_function_defs, _make_parser, parse_target


class SanitizationError(Exception):
    pass


def _strip_fences(raw: str) -> str:
    lines = raw.strip().splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines)


def sanitize_output(raw: str, target_indent_cols: int) -> str:
    """Turn raw model output into exactly one correctly-indented node.

    Mechanical, not prompt-dependent: open-weight models wrap output in
    fences and guess indentation no matter what the prompt says, so the
    guarantee lives here.
    """
    text = _strip_fences(raw)
    text = textwrap.dedent(text).strip("\n")
    if not text:
        raise SanitizationError("Model returned empty output.")

    parser = _make_parser()
    root = parser.parse(text.encode()).root_node

    if root.has_error:
        raise SanitizationError(
            "Output did not parse as valid Python. Return only the "
            "replacement function or class body, with no prose."
        )

    definitions = [
        c for c in root.children
        if c.type in ("function_definition", "class_definition")
    ]
    if len(definitions) != 1 or len(root.children) != 1:
        raise SanitizationError(
            f"Expected exactly one function or class definition and nothing "
            f"else, got {len(root.children)} top-level node(s). Return only "
            f"the replacement node."
        )

    if target_indent_cols:
        text = textwrap.indent(text, " " * target_indent_cols)
    return text + "\n"


def _resolve_target_node(source: bytes, qualifier: str):
    from angrist.ast_guard import AmbiguousTargetError, TargetNotFoundError

    class_name, func_name = parse_target(qualifier)
    tree = _make_parser().parse(source)

    matches = []
    for node, _ in _iter_function_defs(tree.root_node, class_name):
        name_node = node.child_by_field_name("name")
        if name_node is not None and name_node.text.decode() == func_name:
            matches.append(node)

    if not matches:
        raise TargetNotFoundError(f"No target matching '{qualifier}' found")
    if len(matches) > 1:
        raise AmbiguousTargetError(
            f"Qualifier '{qualifier}' matches {len(matches)} nodes"
        )
    return matches[0]


def target_indent(file_path: str | Path, qualifier: str) -> int:
    source = Path(file_path).read_bytes()
    node = _resolve_target_node(source, qualifier)
    return node.start_point[1]


def apply_patch(file_path: str | Path, qualifier: str, new_node_source: str) -> None:
    path = Path(file_path)
    source = path.read_bytes()
    node = _resolve_target_node(source, qualifier)

    new_bytes = new_node_source.encode()
    if not new_bytes.endswith(b"\n"):
        new_bytes += b"\n"
    # node.start_byte sits at the first character of the definition, past
    # its leading indentation; sanitize_output already re-indented the
    # replacement, so trim its leading whitespace on the first line to
    # avoid doubling it.
    line_start = source.rfind(b"\n", 0, node.start_byte) + 1
    leading = source[line_start:node.start_byte]
    if leading.strip() == b"" and new_bytes.startswith(leading):
        new_bytes = new_bytes[len(leading):]

    updated = source[: node.start_byte] + new_bytes + source[node.end_byte :]
    path.write_bytes(updated)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_patcher.py -v`
Expected: PASS for all 15 tests in the file (Task 5 + Task 6).

- [ ] **Step 5: Commit**

```bash
git add angrist/patcher.py tests/test_patcher.py
git commit -m "feat: add deterministic output sanitization and patch application"
```

---

### Task 7: CLI wiring and end-to-end integration test

**Files:**
- Create: `angrist/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `WorktreeSandbox`, `current_branch` (Task 2, `angrist.sandbox`)
  - `extract_node_source`, `validate_scope_source`, `TargetNotFoundError`,
    `AmbiguousTargetError`, `ASTScopeViolationError` (Tasks 3-4,
    `angrist.ast_guard`)
  - `LLMClient`, `OpenAICompatibleClient`, `build_patch_prompt`,
    `sanitize_output`, `target_indent`, `SanitizationError`,
    `apply_patch` (Tasks 5-6, `angrist.patcher`)
- Produces: `app` (Typer instance, entry point `angrist` per
  `pyproject.toml`), function `run_fix(...)` (the testable core, called
  by the Typer command) with signature:

```python
def run_fix(
    file_path: str,
    target: str,
    instruction: str,
    llm_client: LLMClient,
    repo_path: str = ".",
    base_branch: str | None = None,   # None -> current branch
    test_cmd: str = "pytest",
    lint_cmd: str = "ruff check",
    auto_merge: bool = False,
    max_retries: int = 3,
) -> dict:
    """Returns a result dict: {"status": "success"|"failed", "branch": str | None,
    "reason": str | None, "diff": str | None}."""
```

- [ ] **Step 1: Write failing integration test with a stub `LLMClient`**

```python
# tests/test_cli.py
import subprocess
from pathlib import Path

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'angrist.cli'`

- [ ] **Step 3: Implement `cli.py`**

```python
# angrist/cli.py
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import typer
from rich.console import Console

from angrist.ast_guard import (
    AmbiguousTargetError,
    ASTScopeViolationError,
    TargetNotFoundError,
    extract_node_source,
    validate_scope_source,
)
from angrist.patcher import (
    LLMClient,
    OpenAICompatibleClient,
    SanitizationError,
    apply_patch,
    build_patch_prompt,
    sanitize_output,
    target_indent,
)
from angrist.sandbox import WorktreeSandbox, current_branch

app = typer.Typer()
console = Console()


def _run(cmd: str, cwd) -> subprocess.CompletedProcess:
    """Run a configured lint/test command.

    Split with shlex and executed without a shell: the command string
    comes from --test-cmd / --lint-cmd, and passing it through a shell
    would make any metacharacter in it (or in a config file supplying
    it) execute as shell code.
    """
    return subprocess.run(
        shlex.split(cmd), cwd=cwd, capture_output=True, text=True
    )


def run_fix(
    file_path: str,
    target: str,
    instruction: str,
    llm_client: LLMClient,
    repo_path: str = ".",
    base_branch: str | None = None,
    test_cmd: str = "pytest",
    lint_cmd: str = "ruff check",
    auto_merge: bool = False,
    max_retries: int = 3,
) -> dict:
    repo_path = Path(repo_path)
    if base_branch is None:
        base_branch = current_branch(repo_path)
    rel_file = Path(file_path).resolve().relative_to(repo_path.resolve())

    sandbox = WorktreeSandbox(base_branch=base_branch, repo_path=repo_path)
    try:
        with sandbox as wt_path:
            sandboxed_file = wt_path / rel_file
            # Baseline source held in memory, never as a scratch file in
            # the worktree -- a scratch file would be swept into the
            # sandbox commit by `git add .`.
            original_source = sandboxed_file.read_text()

            # Baseline validation run: real repos have pre-existing lint
            # noise and failing tests. Gating on absolute exit codes would
            # fail every run regardless of the patch, so record the
            # starting state and compare deltas later.
            baseline_lint = _run(lint_cmd, wt_path)
            baseline_test = _run(test_cmd, wt_path)

            indent_cols = target_indent(sandboxed_file, target)

            failure_detail = None
            patched = False
            for attempt in range(1, max_retries + 1):
                target_source = extract_node_source(sandboxed_file, target)
                prompt = build_patch_prompt(target_source, instruction, failure_detail)
                raw = llm_client.complete(prompt)

                try:
                    clean = sanitize_output(raw, indent_cols)
                    apply_patch(sandboxed_file, target, clean)
                    validate_scope_source(
                        original_source, sandboxed_file.read_text(), target
                    )
                    patched = True
                    break
                except (SanitizationError, ASTScopeViolationError) as e:
                    failure_detail = str(e)
                    # restore pristine source before the next attempt
                    sandboxed_file.write_text(original_source)

            if not patched:
                return {
                    "status": "failed",
                    "branch": None,
                    "reason": (
                        f"no in-scope patch after {max_retries} attempts; "
                        f"last rejection: {failure_detail}"
                    ),
                    "diff": None,
                }

            lint_result = _run(lint_cmd, wt_path)
            if (
                lint_result.returncode != 0
                and baseline_lint.returncode == 0
            ):
                return {
                    "status": "failed",
                    "branch": sandbox.branch_name,
                    "reason": (
                        "lint regressed (clean before the patch): "
                        f"{lint_result.stdout}\n{lint_result.stderr}"
                    ),
                    "diff": None,
                }

            test_result = _run(test_cmd, wt_path)
            if (
                test_result.returncode != 0
                and baseline_test.returncode == 0
            ):
                return {
                    "status": "failed",
                    "branch": sandbox.branch_name,
                    "reason": (
                        "tests regressed (passing before the patch): "
                        f"{test_result.stdout}\n{test_result.stderr}"
                    ),
                    "diff": None,
                }
            if test_result.returncode != 0 and baseline_test.returncode != 0:
                return {
                    "status": "failed",
                    "branch": sandbox.branch_name,
                    "reason": (
                        "tests still failing after the patch (they were "
                        "already failing at baseline, so this fix did not "
                        f"land): {test_result.stdout}\n{test_result.stderr}"
                    ),
                    "diff": None,
                }

            diff = subprocess.run(
                ["git", "diff", base_branch], cwd=wt_path, capture_output=True, text=True
            ).stdout

            subprocess.run(
                ["git", "add", "."], cwd=wt_path, check=True, capture_output=True, text=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"fix: {instruction}"],
                cwd=wt_path,
                check=True,
                capture_output=True,
                text=True,
            )

            branch_name = sandbox.branch_name

            if auto_merge:
                subprocess.run(
                    ["git", "merge", branch_name],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                sandbox.cleanup()

            return {
                "status": "success",
                "branch": branch_name,
                "reason": None,
                "diff": diff,
            }

    except (TargetNotFoundError, AmbiguousTargetError) as e:
        return {"status": "failed", "branch": None, "reason": str(e), "diff": None}


@app.command()
def fix(
    file: str = typer.Option(..., help="Source file containing the target"),
    target: str = typer.Option(..., help="function_name or ClassName.method_name"),
    instruction: str = typer.Option(None, help="Free-text fix instruction"),
    instruction_file: str = typer.Option(None, help="Path to long-form instruction text"),
    test_cmd: str = typer.Option("pytest"),
    lint_cmd: str = typer.Option("ruff check"),
    auto_merge: bool = typer.Option(False),
    base_branch: str = typer.Option(None, help="Defaults to the repo's current branch"),
):
    if instruction is None and instruction_file is None:
        console.print("[red]Provide --instruction or --instruction-file[/red]")
        raise typer.Exit(code=1)
    if instruction is None:
        instruction = Path(instruction_file).read_text()

    llm_client = OpenAICompatibleClient(
        base_url=os.environ.get("ANGRIST_LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.environ.get("ANGRIST_LLM_API_KEY", ""),
        model=os.environ.get("ANGRIST_LLM_MODEL", "gpt-oss"),
    )

    result = run_fix(
        file_path=file,
        target=target,
        instruction=instruction,
        llm_client=llm_client,
        test_cmd=test_cmd,
        lint_cmd=lint_cmd,
        auto_merge=auto_merge,
        base_branch=base_branch,
    )

    if result["status"] == "success":
        console.print(f"[green]Success[/green] on branch {result['branch']}")
        if result["diff"]:
            console.print(result["diff"])
    else:
        console.print(f"[red]Failed[/red]: {result['reason']}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS for all 6 tests.

Note on the violating-fix test: `sanitize_output` rejects multi-node
output before the guard ever sees it, so that attempt fails as a
`SanitizationError` rather than an `ASTScopeViolationError`. Both are
handled by the same retry branch and both feed their message back, so
the assertions hold either way — the point of the test is that attempt
1 is rejected and attempt 2 is accepted.

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: PASS for all tests across `test_sandbox.py`, `test_ast_guard.py`,
`test_patcher.py`, `test_cli.py`.

- [ ] **Step 6: Commit**

```bash
git add angrist/cli.py tests/test_cli.py
git commit -m "feat: add CLI wiring with scope/lint/test/merge flow"
```

---

## Review Fixes Applied

This plan was audited after its first draft. Eight defects were found in
the original task code and corrected here — recorded so a reader does not
reintroduce them:

1. **Class-method scope hole** (critical): the original `validate_scope`
   whitelisted the entire enclosing `class_definition`, letting the model
   silently rewrite every sibling method while the guard passed. Task 4
   now descends into the class body and protects members individually,
   with `test_validate_scope_rejects_sibling_method_edit` as the guard.
2. **Snapshot file leaked into the commit**: `run_fix` wrote
   `<name>.orig-snapshot` inside the worktree, which `git add .` then
   committed. The baseline is now held in memory.
3. **No fence stripping**: model output wrapped in ```` ``` ```` would be
   injected verbatim, corrupting the file. `sanitize_output` (Task 6)
   handles it mechanically rather than trusting the prompt.
4. **Worktree created inside the repo**: polluted the main workspace's
   `git status` and test collection, contradicting the zero-dirty-state
   claim. Now created under the system temp dir.
5. **Absolute lint/test gate**: any pre-existing failure in a real repo
   would fail every run forever. Now a delta against a baseline run.
6. **Undefined indentation contract**: class methods start at column 4;
   column-0 model output broke the file. `target_indent` +
   `sanitize_output` normalize it.
7. **Dead `for...else` branch** in the retry loop (unreachable, since the
   final attempt raised inside the loop). Replaced with a `patched` flag.
8. **Hardcoded `master` base branch**: now defaults to the repo's current
   branch via `current_branch()`.

Additionally, `_run` uses `shlex.split` without `shell=True`, so a
metacharacter in `--test-cmd` / `--lint-cmd` cannot execute as shell code.

## Self-Review Notes

- **Spec coverage:** Problem/Solution -> Tasks 2-4 (worktree + AST
  guard). Scope (MVP) language/target/LLM/patch/merge constraints ->
  reflected in Global Constraints and Task 5-7 signatures. Architecture
  diagram steps 1-5 -> `run_fix` in Task 7 implements the full sequence
  including retry loop and rollback. CLI Flags table -> `fix` command
  options in Task 7. Error Handling section -> exception handling in
  `run_fix` (violation retries, lint/test failure, unhandled exception
  cleanup via `WorktreeSandbox.__exit__`). Testing section -> matches
  Task 2 (sandbox unit tests), Task 3-4 (ast_guard unit tests), Task 5-6
  (patcher unit tests with stub client), Task 7 (CLI integration test
  with stub LLM).
- **Placeholder scan:** none found; every step has concrete code.
- **Type consistency:** `LLMClient.complete(prompt: str) -> str` used
  identically in Task 5 definition, Task 7 `run_fix` call site, and test
  stubs. `extract_node_source`, `validate_scope`, `apply_patch`,
  `target_indent` all take `(path, qualifier, ...)` consistently across
  Tasks 3, 4, 6, 7. `run_fix` calls `validate_scope_source` (string
  form, defined in Task 4) rather than the path form, because its
  baseline lives in memory. `sanitize_output(raw, indent)` signature
  matches between Task 6's definition and Task 7's call site.
- **Spec coverage of the review fixes:** worktree location, base-branch
  detection, method-level guard granularity, in-memory baseline,
  sanitization, and delta validation are all now stated in the spec as
  well as implemented in the plan, so the two documents agree.
