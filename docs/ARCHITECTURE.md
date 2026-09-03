# Angrist Architecture & Design

This document details the architectural design, security invariants, and algorithmic internals of Angrist.

---

## 1. Design Philosophy & Core Invariants

Angrist is engineered around a single foundational premise: **An AI code repair agent should never have write permission to the wider codebase.**

Traditional coding assistants operate with broad file-level or repository-level write permissions. While powerful for greenfield scaffolding, this unconstrained approach introduces severe risks during bug repair:
- Hallucinated edits in unrelated functions.
- Accidental removal of comments, docstrings, or type annotations.
- Silent modifications to uncalled top-level blocks or module variables.
- Repository corruption when interrupted mid-flight.

Angrist replaces heuristic trust with mathematical AST constraints and operating system process isolation.

```
+-----------------------------------------------------------------------------+
|                               Core Invariants                               |
|                                                                             |
|  1. Scope Lock: Delta AST(before, after) contains exactly the target node.   |
|  2. Sandbox Isolation: All patches execute in ephemeral Git worktrees.      |
|  3. Conservative Gates: Candidate never passes if any new failure occurs.   |
|  4. Idempotent Cleanup: Worktrees and branches are cleaned on exit.         |
+-----------------------------------------------------------------------------+
```

---

## 2. System Architecture

Angrist consists of four decoupled subsystems operating in a strict, unidirectional pipeline:

```
[ User CLI / Script ]
         │
         ▼
[ 1. AST Guard ] ────────── Parses source, resolves target node, validates scope
         │
         ▼
[ 2. Sandbox Engine ] ───── Spawns ephemeral Git worktree & isolates environment
         │
         ▼
[ 3. LLM Patcher ] ──────── Prompts model, sanitizes code fences, applies edits
         │
         ▼
[ 4. Delta Gating ] ─────── Runs pre/post tests & linters, detects regressions
```

---

## 3. Subsystem Deep-Dive

### 3.1 AST Scope Guard (`angrist/ast_guard.py`)

The AST Guard is the security perimeter of Angrist. It uses Tree-sitter to parse the Python source code into a concrete syntax tree (CST).

#### Target Resolution
The user specifies a target using dot-notation:
- Top-level function: `function_name`
- Class method: `ClassName.method_name`
- Nested class method: `OuterClass.InnerClass.method_name`

The resolver traverses the syntax tree, inspecting `class_definition`, `function_definition`, and `decorated_definition` nodes. For decorated definitions, the AST guard automatically unwraps the inner function or class while preserving the outer decorator byte range.

#### Structural Occurrence Indexing
Naive AST comparison using character or byte offsets fails when an earlier function changes in length, shifting the offsets of all subsequent functions in the file.

Angrist solves this by mapping every node to an immutable structural key:
```python
key = (parent_scope_name, node.type, node_name, occurrence_index)
```

- `parent_scope_name`: The enclosing class or module root.
- `node.type`: The Tree-sitter grammar type (e.g. `function_definition`, `expression_statement`).
- `node_name`: The identifier name, or empty for anonymous nodes (such as `if __name__ == "__main__":`).
- `occurrence_index`: A zero-indexed counter distinguishing duplicate identical structures within the same scope.

When candidate code is submitted, Angrist compares the structural map of the original file against the candidate file:
1. Every non-target node must have byte-for-byte identical content.
2. The target node must exist in the candidate AST (preventing accidental deletion or renaming).
3. Any added top-level statements must not collide with existing names.
4. Any discrepancy outside the target node raises an `ASTScopeViolationError`, triggering an immediate rollback.

---

### 3.2 Git-Worktree Sandbox Isolation (`angrist/sandbox.py`)

All destructive operations (writing candidate patches, running test suites, executing linters) occur inside an isolated Git worktree:

1. `WorktreeSandbox.__enter__`:
   - Checks out a new branch (`angrist-sandbox-<uuid>`) based on the target base branch.
   - Attaches the branch to an ephemeral directory under the system temporary directory (`$TEMP/angrist-sandbox-<uuid>`).
   - The user's active working directory and branch remain completely untouched.
2. Environment Isolation:
   - Prepends the sandbox root directory to `PYTHONPATH` during subprocess execution, ensuring local modules are imported without requiring editable package re-installation.
3. Windows-Safe Atomic Cleanup:
   - On Windows, `.git` repository metadata contains read-only attribute flags that cause standard `shutil.rmtree` calls to fail with `PermissionError: [WinError 5] Access is denied`.
   - Angrist uses Python 3.12+ `onexc` callbacks (`_handle_remove_readonly`) to clear read-only attributes before deletion, ensuring zero disk leaks.

---

### 3.3 LLM Patcher & Sanitizer (`angrist/patcher.py`)

The patcher manages communication with LLM backends:

1. **Prompt Construction:**
   - Extracts only the source code of the target function.
   - Formulates a system prompt demanding that the model output strictly the replacement function definition.
   - If an earlier attempt violated AST scope, the prompt includes the exact rejection reason to guide the model.
2. **Indentation-Aware Sanitization:**
   - Detects the indentation level of the target node in the enclosing file (e.g. 0 spaces for top-level functions, 4 spaces for class methods, 8 spaces for nested methods).
   - Strips markdown code fences (` ```python `) and extraneous prose commentary.
   - Dedents or re-indents the model output to match the target column exactly.
   - Verifies that the sanitized output parses as exactly one function or class definition.

---

### 3.4 Conservative Dual Delta Gating (`angrist/cli.py`)

A patch must not only be syntactically valid; it must also prove that it improves the codebase without introducing regressions.

#### 1. Baseline Pre-flight Check
Before sending any tokens to the LLM, Angrist runs baseline tests and linters on the unmodified code. If the test runner exits with an abnormal code (e.g. exit code 3 for collection error, 4 for CLI syntax error) or the linter is not installed, Angrist aborts immediately with a clear error message.

#### 2. Test Delta Gate
Angrist parses both `FAILED` and `ERROR` test results from the test runner:
- Baseline failures are tracked: `base_failed = {"test_a", "test_b"}`.
- Candidate failures are tracked: `cand_failed = {"test_a"}`.
- New failures trigger an instant failure: `new_failures = cand_failed - base_failed`.
- If candidate exits non-zero, it never silently passes. Partial fixes are diagnosed accurately (`"tests still failing after the patch (1 test(s) failed): test_a"`).

#### 3. Set-Based Lint Delta Gate
Linters like Ruff modernly output multi-line diagnostic blocks with context lines. A change in function length shifts line numbers in subsequent warnings.
Angrist extracts line-independent `(filename, rule_code)` signatures:
- Supports JSON output via `ruff check --output-format=json`.
- Supports concise format regex for tools like `flake8`, `mypy`, and `pylint`.
- Subtracts rule signatures: `new_findings = cand_findings - base_findings`.
- If candidate exits non-zero without parsable findings on stdout, it is conservatively rejected.

---

## 4. Benchmark Evaluation Methodology (`angrist/benchmark.py`)

Angrist includes a native benchmark runner evaluating performance against curated SWE-bench Lite instances:
- Instances are defined declaratively in `benchmarks/swe_bench/manifest.json`.
- Each instance runs within a dedicated temporary worktree sandbox.
- Results are collected in memory and rendered using Rich terminal tables.
- Machine-readable metrics are exported to JSON for automated CI verification.
