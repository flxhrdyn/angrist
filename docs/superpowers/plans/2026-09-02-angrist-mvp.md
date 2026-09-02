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
  - `class WorktreeSandbox` — constructor
    `WorktreeSandbox(base_branch: str, repo_path: str | Path = ".")`.
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

from angrist.sandbox import WorktreeSandbox


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
    return repo


def test_enter_creates_worktree_and_branch(git_repo):
    with WorktreeSandbox(base_branch="master", repo_path=git_repo) as wt_path:
        assert wt_path.exists()
        assert (wt_path / "a.txt").read_text() == "hello\n"

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
import uuid
from pathlib import Path


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
        self.worktree_path = self.repo_path / f".angrist-sandbox-{suffix}"
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
  - `validate_scope(original_path: str | Path, candidate_path: str | Path, qualifier: str) -> None`
    — raises `ASTScopeViolationError` with a descriptive message if the
    candidate file violates the whitelist; returns `None` on success.
    Message must name the offending node (name + type) so callers can
    feed it back into a retry prompt.

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ast_guard.py -v -k validate_scope`
Expected: FAIL with `ImportError: cannot import name 'validate_scope'`

- [ ] **Step 3: Implement `validate_scope`**

```python
# angrist/ast_guard.py (append)

_ALLOWED_TARGET_TYPES = {"function_definition", "class_definition"}


def _top_level_signature(source: bytes, node):
    """A stable identity for a top-level node: (type, name-or-None)."""
    name_node = node.child_by_field_name("name")
    name = name_node.text.decode() if name_node is not None else None
    return node.type, name


def validate_scope(
    original_path: str | Path, candidate_path: str | Path, qualifier: str
) -> None:
    class_name, func_name = parse_target(qualifier)
    orig_source = Path(original_path).read_bytes()
    cand_source = Path(candidate_path).read_bytes()

    parser = _make_parser()
    orig_tree = parser.parse(orig_source)
    cand_tree = parser.parse(cand_source)

    orig_top = list(orig_tree.root_node.children)
    cand_top = list(cand_tree.root_node.children)

    def node_text(source, node):
        return source[node.start_byte:node.end_byte]

    def is_target_or_import(source, node):
        if node.type == "import_statement" or node.type == "import_from_statement":
            return True
        if class_name is None and node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.text.decode() == func_name:
                return True
        if class_name is not None and node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.text.decode() == class_name:
                return True
        return False

    # Build lookup of original non-target, non-import top-level nodes by
    # (type, name) signature -> exact source bytes, to check they survive
    # byte-identical in the candidate.
    orig_protected = {}
    for node in orig_top:
        if is_target_or_import(orig_source, node):
            continue
        sig = _top_level_signature(orig_source, node)
        orig_protected[sig] = node_text(orig_source, node)

    orig_top_names = set()
    for node in orig_top:
        sig = _top_level_signature(orig_source, node)
        if sig[1] is not None:
            orig_top_names.add(sig[1])

    cand_protected = {}
    cand_new_names = set()
    for node in cand_top:
        if is_target_or_import(cand_source, node):
            continue
        sig = _top_level_signature(cand_source, node)
        name = sig[1]
        if name is not None and name not in orig_top_names:
            # net-new top-level node
            if name in cand_new_names:
                raise ASTScopeViolationError(
                    f"Candidate defines '{name}' more than once at top level"
                )
            cand_new_names.add(name)
            continue
        cand_protected[sig] = node_text(cand_source, node)

    # Every original protected node must survive byte-identical.
    for sig, orig_bytes in orig_protected.items():
        if sig not in cand_protected:
            raise ASTScopeViolationError(
                f"Node {sig[0]} '{sig[1]}' present in original but missing "
                f"or modified in candidate (outside allowed scope)"
            )
        if cand_protected[sig] != orig_bytes:
            raise ASTScopeViolationError(
                f"Node {sig[0]} '{sig[1]}' was modified outside the "
                f"whitelisted scope (target: '{qualifier}')"
            )

    # No original protected node may have been removed and no extra
    # protected-signature node may appear that wasn't in original.
    for sig in cand_protected:
        if sig not in orig_protected:
            raise ASTScopeViolationError(
                f"Node {sig[0]} '{sig[1]}' in candidate does not match any "
                f"original node and is not a recognized net-new top-level "
                f"addition (outside allowed scope)"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ast_guard.py -v`
Expected: PASS for all tests in the file (11 total from Task 3 + 4)

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

### Task 6: Patch application (write candidate into file)

**Files:**
- Modify: `angrist/patcher.py` (add `apply_patch`)
- Test: `tests/test_patcher.py` (append)

**Interfaces:**
- Consumes: `extract_node_source` from Task 3 (`angrist.ast_guard`).
- Produces:
  - `apply_patch(file_path: str | Path, qualifier: str, new_node_source: str) -> None`
    — replaces the addressed node's exact source span in `file_path`
    with `new_node_source`, writing the file in place. Raises
    `angrist.ast_guard.TargetNotFoundError` /
    `AmbiguousTargetError` under the same conditions as
    `extract_node_source` (reuses the same resolution logic).

- [ ] **Step 1: Write failing test for `apply_patch`**

```python
# tests/test_patcher.py (append)
from pathlib import Path

from angrist.patcher import apply_patch


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

Run: `pytest tests/test_patcher.py -v -k apply_patch`
Expected: FAIL with `ImportError: cannot import name 'apply_patch'`

- [ ] **Step 3: Implement `apply_patch`**

```python
# angrist/patcher.py (append)
from pathlib import Path as _Path  # already imported as Path below if needed

from angrist.ast_guard import _iter_function_defs, _make_parser, parse_target


def apply_patch(file_path: str | Path, qualifier: str, new_node_source: str) -> None:
    from angrist.ast_guard import AmbiguousTargetError, TargetNotFoundError

    class_name, func_name = parse_target(qualifier)
    path = Path(file_path)
    source = path.read_bytes()
    parser = _make_parser()
    tree = parser.parse(source)

    matches = []
    for node, _ in _iter_function_defs(tree.root_node, class_name):
        name_node = node.child_by_field_name("name")
        if name_node is not None and name_node.text.decode() == func_name:
            matches.append(node)

    if not matches:
        raise TargetNotFoundError(f"No target matching '{qualifier}' found in {file_path}")
    if len(matches) > 1:
        raise AmbiguousTargetError(
            f"Qualifier '{qualifier}' matches {len(matches)} nodes in {file_path}"
        )

    node = matches[0]
    new_bytes = new_node_source.encode()
    if not new_bytes.endswith(b"\n"):
        new_bytes += b"\n"
    updated = source[: node.start_byte] + new_bytes + source[node.end_byte :]
    path.write_bytes(updated)
```

Note: add `from pathlib import Path` at the top of `patcher.py` if not
already present from Task 5 (it isn't — add it now).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_patcher.py -v`
Expected: PASS for all 6 tests

- [ ] **Step 5: Commit**

```bash
git add angrist/patcher.py tests/test_patcher.py
git commit -m "feat: add apply_patch to write LLM output into target node"
```

---

### Task 7: CLI wiring and end-to-end integration test

**Files:**
- Create: `angrist/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `WorktreeSandbox` (Task 2, `angrist.sandbox`)
  - `extract_node_source`, `validate_scope`, `TargetNotFoundError`,
    `AmbiguousTargetError`, `ASTScopeViolationError` (Tasks 3-4,
    `angrist.ast_guard`)
  - `LLMClient`, `OpenAICompatibleClient`, `build_patch_prompt`,
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
    base_branch: str = "master",
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
        lint_cmd="python -c \"pass\"",  # no-op lint to avoid ruff dependency in test
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
    bad_fix = (
        "def add(a, b):\n    return a + b\n\n\n"
        "def unrelated():\n    pass\n"
    )
    # first attempt touches nothing extra actually - force a real violation:
    # overwrite an existing unrelated node instead
    (git_repo_with_bug / "mod.py").write_text(
        "def add(a, b):\n    return a - b\n\n\ndef other(x):\n    return x\n"
    )
    subprocess.run(["git", "add", "."], cwd=git_repo_with_bug, check=True)
    subprocess.run(["git", "commit", "-m", "add other"], cwd=git_repo_with_bug, check=True)

    violating_fix = "def add(a, b):\n    return a + b\n"
    good_fix = "def add(a, b):\n    return a + b\n"
    client = StubLLMClient([violating_fix, good_fix])

    result = run_fix(
        file_path=str(git_repo_with_bug / "mod.py"),
        target="add",
        instruction="fix the bug",
        llm_client=client,
        repo_path=str(git_repo_with_bug),
        base_branch="master",
        test_cmd="python -c \"pass\"",
        lint_cmd="python -c \"pass\"",
        auto_merge=False,
    )

    assert result["status"] == "success"
    assert len(client.prompts) >= 1


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
        lint_cmd="python -c \"pass\"",
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
import subprocess
from pathlib import Path

import typer
from rich.console import Console

from angrist.ast_guard import (
    AmbiguousTargetError,
    ASTScopeViolationError,
    TargetNotFoundError,
    extract_node_source,
    validate_scope,
)
from angrist.patcher import (
    LLMClient,
    OpenAICompatibleClient,
    apply_patch,
    build_patch_prompt,
)
from angrist.sandbox import WorktreeSandbox

app = typer.Typer()
console = Console()


def run_fix(
    file_path: str,
    target: str,
    instruction: str,
    llm_client: LLMClient,
    repo_path: str = ".",
    base_branch: str = "master",
    test_cmd: str = "pytest",
    lint_cmd: str = "ruff check",
    auto_merge: bool = False,
    max_retries: int = 3,
) -> dict:
    repo_path = Path(repo_path)
    rel_file = Path(file_path).resolve().relative_to(repo_path.resolve())

    sandbox = WorktreeSandbox(base_branch=base_branch, repo_path=repo_path)
    try:
        with sandbox as wt_path:
            sandboxed_file = wt_path / rel_file
            original_snapshot = wt_path / f"{rel_file.name}.orig-snapshot"
            original_snapshot.write_bytes(sandboxed_file.read_bytes())

            violation_detail = None
            for attempt in range(1, max_retries + 1):
                target_source = extract_node_source(sandboxed_file, target)
                prompt = build_patch_prompt(target_source, instruction, violation_detail)
                new_source = llm_client.complete(prompt)

                apply_patch(sandboxed_file, target, new_source)

                try:
                    validate_scope(original_snapshot, sandboxed_file, target)
                    break
                except ASTScopeViolationError as e:
                    violation_detail = str(e)
                    # restore original before next retry
                    sandboxed_file.write_bytes(original_snapshot.read_bytes())
                    if attempt == max_retries:
                        raise
            else:
                raise ASTScopeViolationError("max retries exhausted")

            lint_result = subprocess.run(
                lint_cmd, shell=True, cwd=wt_path, capture_output=True, text=True
            )
            if lint_result.returncode != 0:
                return {
                    "status": "failed",
                    "branch": sandbox.branch_name,
                    "reason": f"lint failed: {lint_result.stdout}\n{lint_result.stderr}",
                    "diff": None,
                }

            test_result = subprocess.run(
                test_cmd, shell=True, cwd=wt_path, capture_output=True, text=True
            )
            if test_result.returncode != 0:
                return {
                    "status": "failed",
                    "branch": sandbox.branch_name,
                    "reason": f"tests failed: {test_result.stdout}\n{test_result.stderr}",
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

    except ASTScopeViolationError as e:
        return {
            "status": "failed",
            "branch": None,
            "reason": f"scope violation after retries: {e}",
            "diff": None,
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
    base_branch: str = typer.Option("master"),
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
Expected: PASS for all 3 tests. If `test_run_fix_retries_on_scope_violation_then_succeeds`
fails because the crafted "violating" fix doesn't actually trigger a
violation (since it doesn't touch `other()`), adjust the test's
`violating_fix` to explicitly include a modified `other` function, e.g.
`"def add(a, b):\n    return a + b\n\n\ndef other(x):\n    return x + 1\n"`,
and re-run.

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
  stubs. `extract_node_source`, `validate_scope`, `apply_patch` all take
  `(path, qualifier, ...)` consistently across Tasks 3, 4, 6, 7.
