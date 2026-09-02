# angrist — Design Spec

## Problem

LLM coding agents rely on prompt engineering to bound edit scope. This is
probabilistic, not enforced: agents over-edit (touch unrelated functions),
leave dirty git state, and burn tokens sending whole files as context.

Existing hosted agents (Claude Code, Cursor) can partially mitigate this
with host-side hooks, but that guardrail only exists inside that host's
own session and tool-call loop. There's no standalone, headless way to
get the same deterministic scope guarantee using a free or self-hosted
open-weight model, independent of any particular agent host.

## Solution

`angrist` is a Python CLI, host-agnostic and headless, that runs a
single-function micro-fix through two hard deterministic guardrails,
targeted at users who want this on free or local/open models rather
than tied to a paid hosted agent:

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
  OpenAI-compatible HTTP API — Groq, local Ollama/vLLM, or any other
  OpenAI-compatible endpoint are interchangeable by config/env, no code
  change. Default provider **Groq** (free tier), default model
  **gpt-oss** (open-weight, also runnable locally for users who want
  it). No LiteLLM dependency.
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
        |                (outside the repo tree, base = current branch)
        v
[3. Baseline Capture]  run lint + test on untouched sandbox, record results
        |
        v
[4. AST-Scoped LLM Patch]  patcher.py — send target node + instruction to LLM
        |
        v
[5. Sanitize]  strip fences, normalize indent, verify it parses
        |
        v
[6. AST Scope Guard]  ast_guard.py — validate candidate vs whitelist
        |
   +----+----+
   | ok | violation or bad output -> retry (max 3, detail fed back)
   v         |
[7. Lint + Test vs baseline]   (retries exhausted -> rollback + report)
   |
 +-+-+
no regression   regression -> rollback + report
   |
[Merge & Clean]  (manual review by default, or --auto-merge)
```

## Components

### `sandbox.py` — `WorktreeSandbox`

Context manager wrapping `git worktree` via `subprocess`.

- `__enter__`: `git worktree add -b <temp-branch> <temp-path> <base-branch>`.
- **Worktree location is outside the repo** — a sibling temp directory
  (system temp dir), never inside the repo tree. A worktree created
  inside the repo would show up in the main workspace's `git status`
  and be collected by the main repo's own test/lint runs, breaking the
  "zero dirty state" guarantee.
- **`base_branch` defaults to the repo's current branch**, detected via
  `git rev-parse --abbrev-ref HEAD` — not a hardcoded `master`/`main`.
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
  - **only the addressed node itself** may differ. When the target is
    `ClassName.method_name`, the whitelist is that *method node*, not
    the enclosing class: every sibling method, class attribute, and
    decorator in that class must still be byte-identical. Validation
    therefore descends into the class body rather than treating the
    whole `class_definition` as the target.
  - import nodes may differ.
  - net-new top-level nodes are allowed, provided their name does not
    collide with any existing top-level name in the file.
  - every other existing node must be byte-identical (strict AST
    equality) between original and candidate.
  - any other difference raises `ASTScopeViolationError`.
- **Original comparison baseline** comes from git
  (`git show <base-branch>:<path>`) or an in-memory snapshot — never a
  scratch file written inside the worktree, which would otherwise be
  swept into the sandbox commit.

### `patcher.py`

- Sends target node text + instruction (from `--instruction` or
  `--instruction-file`) to the LLM via `LLMClient`.
- `LLMClient` is a small protocol (`complete(prompt) -> str`) backed by
  an OpenAI-compatible HTTP client, so Groq, OpenAI, Ollama, vLLM are
  all interchangeable by config/env — no LiteLLM needed for this.
- **Deterministic output sanitization** before anything is written.
  Free/open-weight models routinely wrap output in markdown fences
  regardless of prompt instructions — relying on the prompt here would
  reintroduce the very probabilistic guardrail this project exists to
  replace. So `patcher.py` mechanically:
  1. strips leading/trailing markdown code fences and any language tag,
  2. re-indents the replacement to the target node's original column
     (class methods start at column 4, not 0 — the model's output
     indentation is normalized, not trusted),
  3. parses the sanitized text with `py-tree-sitter` and rejects it if
     it does not parse as a single valid function/class definition.
  A sanitization failure is treated exactly like a scope violation:
  detail is fed back and the attempt is retried.
- Receives the full replacement text, writes it into the file inside
  the sandbox worktree, replacing the old node.

### `cli.py`

Wires the flow with `Typer` + `Rich` status output:

1. Resolve target, extract node.
2. Enter `WorktreeSandbox`.
3. **Baseline capture**: run `--lint-cmd` and `--test-cmd` in the
   untouched sandbox first and record their results. Real repos have
   pre-existing lint noise and already-failing tests; gating on
   absolute exit code would make every run fail regardless of the fix.
   The gate is a *delta*: no test that passed at baseline may fail
   after the patch, and no new lint finding may appear.
4. Patch loop: send to LLM, sanitize output, guard-check candidate.
   - Violation or sanitization failure: feed detail back into next
     prompt, retry (max 3 attempts total). Exhausted -> rollback,
     report failure.
5. Guard pass -> re-run `--lint-cmd` (default `ruff check`) and
   `--test-cmd` (default `pytest`) inside the sandbox, compare against
   baseline.
   - Regression vs baseline -> rollback, report failure.
6. No regression -> print diff summary. If `--auto-merge`, merge
   sandbox branch into base and clean up worktree; otherwise leave
   branch in place for manual review/merge.

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
- Sanitization failure (unstrippable fences, output that does not parse
  as a single function/class node) -> same handling as a scope
  violation: detail fed back, retry within the 3-attempt budget.
- Lint or test *regression vs baseline* post-guard -> rollback + report
  which tests newly failed or which lint findings are new. Pre-existing
  failures present at baseline never fail the run.
- Any unhandled exception inside the sandbox context -> worktree/branch
  force-removed by `WorktreeSandbox.__exit__`; main workspace
  unaffected.

## Key Risk (unvalidated)

The value proposition assumes a free-tier or locally-hosted
open-weight model can produce a correct, in-scope, full-node
replacement often enough to be useful. This has not been measured. If
the violation or incorrectness rate is high, the 3-attempt budget
burns without producing a usable fix and the tool feels broken.

**Mitigation before heavy investment:** run a throwaway spike against
~10 real broken functions using the intended default (Groq +
`gpt-oss`), measuring (a) scope-violation rate, (b) sanitization
failure rate, (c) fix correctness rate. If violation rates are high,
the design still holds — the guard correctly rejects bad output — but
the retry budget and prompt shape need tuning before the CLI is worth
polishing.

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
  top-level name, **edited sibling method inside the target's own
  class**).
- `patcher.py`: unit tests with a stubbed `LLMClient` — no live API
  calls in test suite. Sanitization tests cover fenced output, fenced
  output with a language tag, column-0 output for a class method, and
  output that does not parse.
- `cli.py`: integration test running the full flow end-to-end against
  a fixture repo with a deliberately broken function, stubbed LLM
  returning a known-good fix, asserting sandbox cleanup / merge
  behavior for both `--auto-merge` and default modes.
