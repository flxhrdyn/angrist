# angrist — Design Spec

## Problem

LLM coding agents rely on prompt engineering to bound edit scope. This is
probabilistic, not enforced: agents over-edit (touch unrelated functions),
leave dirty git state, and burn tokens sending whole files as context.

## Solution

`angrist` is a Python CLI that runs a single-function micro-fix through two
hard deterministic guardrails:

1. **Git worktree isolation** — all edits and test runs happen in a
   temporary worktree; the main workspace is never touched mid-run.
2. **AST scope lock** — using `py-tree-sitter`, the agent is only ever
   shown the target function/class node, and any edit outside a
   whitelisted scope (target node + imports + net-new top-level
   nodes) is physically rejected and triggers rollback.

## Scope (MVP)

- Language: **Python only**.
- Target selection: **manual only** (`--file` + `--target`), no
  stack-trace auto-parsing.
- LLM: **provider-agnostic** via a thin `LLMClient` protocol over an
  OpenAI-compatible HTTP API. Default provider **Groq**, default model
  **gpt-oss**. No LiteLLM dependency.
- Patch strategy: **full-node-replace** (LLM returns the complete new
  function/class body; guard re-parses whole file and swaps the node).
  No unified-diff patching.
- Merge: **manual by default** — on success, sandbox branch + diff
  summary are left for the user to review/merge. `--auto-merge` flag
  opts into automatic merge + worktree cleanup.

Out of scope for MVP: multi-language support, stack-trace parsing,
LiteLLM, diff-based patching.

## Architecture

```
User Request (--file, --target, --instruction)
        |
        v
[1. Target Scoper]  ast_guard.py — resolve qualifier, extract target node
        |
        v
[2. Worktree Sandbox]  sandbox.py — spawn isolated worktree + branch
        |
        v
[3. AST-Scoped LLM Patch]  patcher.py — send target node + instruction to LLM
        |
        v
[4. AST Scope Guard]  ast_guard.py — validate candidate vs whitelist
        |
   +----+----+
   | ok | violation -> retry (max 3, violation detail fed back)
   v         |
[5. Lint + Test]      (retries exhausted -> rollback + report)
   |
 +-+-+
pass  fail -> rollback + report
   |
[Merge & Clean]  (manual review by default, or --auto-merge)
```

## Components

### `sandbox.py` — `WorktreeSandbox`

Context manager wrapping `git worktree` via `subprocess`.

- `__enter__`: `git worktree add -b <temp-branch> <temp-path> <base-branch>`.
- `__exit__`: on exception, `git worktree remove --force` + delete temp
  branch. On clean success, worktree/branch are left in place (caller
  decides merge/cleanup) unless `--auto-merge` was requested, in which
  case the CLI performs merge + removes the worktree/branch itself.
- Guarantees the main workspace is never touched by the run.

### `ast_guard.py` — target resolution + scope guard

- **Target addressing**: `file::ClassName.method_name` or
  `file::function_name`. The qualifier disambiguates duplicate names
  (nested classes, multiple classes with same method name).
- **Extraction**: parses the file with `py-tree-sitter`, locates the
  addressed node, returns its source text (this, not the whole file,
  is what gets sent to the LLM).
- **Validation** (`ASTScopeViolationError` on failure): given the
  original file AST and the candidate (post-patch) file AST —
  - target node may differ (that's the fix).
  - import nodes may differ.
  - net-new top-level nodes are allowed, provided their name does not
    collide with any existing top-level name in the file.
  - every other existing node must be byte-identical (strict AST
    equality) between original and candidate.
  - any other difference raises `ASTScopeViolationError`.

### `patcher.py`

- Sends target node text + instruction (from `--instruction` or
  `--instruction-file`) to the LLM via `LLMClient`.
- `LLMClient` is a small protocol (`complete(prompt) -> str`) backed by
  an OpenAI-compatible HTTP client, so Groq, OpenAI, Ollama, vLLM are
  all interchangeable by config/env — no LiteLLM needed for this.
- Receives the full replacement text, writes it into the file inside
  the sandbox worktree, replacing the old node.

### `cli.py`

Wires the flow with `Typer` + `Rich` status output:

1. Resolve target, extract node.
2. Enter `WorktreeSandbox`.
3. Patch loop: send to LLM, guard-check candidate.
   - Violation: feed violation detail back into next prompt, retry
     (max 3 attempts total). Exhausted -> rollback, report failure.
4. Guard pass -> run `--lint-cmd` (default `ruff check`), then
   `--test-cmd` (default `pytest`) inside the sandbox.
   - Either fails -> rollback, report failure.
5. Both pass -> print diff summary. If `--auto-merge`, merge sandbox
   branch into base and clean up worktree; otherwise leave branch in
   place for manual review/merge.

## CLI Flags

| Flag | Required | Default | Purpose |
|---|---|---|---|
| `--file` | yes | - | Source file containing target |
| `--target` | yes | - | Qualifier: `function_name` or `ClassName.method_name` |
| `--instruction` | one of these two | - | Free-text fix instruction |
| `--instruction-file` | | - | Path to long-form instruction text |
| `--test-cmd` | no | `pytest` | Test command run inside sandbox |
| `--lint-cmd` | no | `ruff check` | Lint command run inside sandbox |
| `--auto-merge` | no | off | Merge + cleanup sandbox automatically on success |

## Error Handling

- Duplicate/ambiguous target without sufficient qualifier -> hard error
  before any LLM call, no sandbox created.
- `ASTScopeViolationError` -> retry with violation detail injected into
  prompt, up to 3 attempts, then rollback + report which node(s) the
  LLM tried to touch.
- Lint or test failure post-guard -> rollback + report failing command
  output.
- Any unhandled exception inside the sandbox context -> worktree/branch
  force-removed by `WorktreeSandbox.__exit__`; main workspace
  unaffected.

## Tech Stack

Python 3.11+, Typer, Rich, py-tree-sitter, native `git worktree` via
`subprocess`, OpenAI-compatible HTTP client (Groq + gpt-oss default).

## Testing

- `sandbox.py`: unit tests against a local throwaway git repo — verify
  worktree created, verify force-cleanup on injected exception, verify
  main workspace untouched.
- `ast_guard.py`: unit tests with fixture Python files — correct
  extraction by qualifier, duplicate-name resolution, whitelist pass
  cases, violation-trigger cases (edited unrelated node, colliding new
  top-level name).
- `patcher.py`: unit tests with a stubbed `LLMClient` — no live API
  calls in test suite.
- `cli.py`: integration test running the full flow end-to-end against
  a fixture repo with a deliberately broken function, stubbed LLM
  returning a known-good fix, asserting sandbox cleanup / merge
  behavior for both `--auto-merge` and default modes.
