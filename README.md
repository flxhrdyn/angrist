# Angrist

> *"As Angrist carved the Silmaril from the Iron Crown of Morgoth: excise the flaw, preserve the tree."*

[![CI](https://github.com/flxhrdyn/angrist/actions/workflows/ci.yml/badge.svg)](https://github.com/flxhrdyn/angrist/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/angrist?color=blue&logo=pypi&logoColor=white)](https://pypi.org/project/angrist/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

Angrist repairs bugs in Python functions using LLMs while strictly locking edits to the target AST node. It tests every patch in an isolated Git worktree before touching your code, preventing unintended modifications across the rest of the file.

![Angrist Demo](demo/demo.gif)

---

## Overview

Most AI coding tools operate with full write access to your files. When asked to fix a bug inside a specific function, models frequently rewrite unrelated lines, remove comments, or break sibling methods.

Angrist prevents this through strict architectural boundaries:

- **Target Scope Locking:** Tree-sitter isolates the exact target function or method. Every byte outside that target node is guaranteed to remain untouched.
- **Isolated Worktrees:** Patches, tests, and linter runs execute in temporary Git worktrees. Your active workspace and uncommitted edits are never modified.
- **Delta Regression Gating:** Candidate patches must pass existing tests and introduce zero new lint errors before they can be merged.
- **Model Agnostic:** Connects to any OpenAI-compatible endpoint, including local models (Ollama, vLLM) and cloud APIs (Groq, OpenAI).



---

## Installation

Install using `uv` (recommended) or `pipx`:

```bash
uv tool install angrist
# or
pipx install angrist
# or for local development
pip install -e ".[dev]"
```

### Dependencies
- Python 3.11+
- Git 2.20+ (for worktree management)
- Tree-sitter & Tree-sitter Python

---

## Configuration

Angrist resolves configuration with the following precedence:
**CLI Flags > Environment Variables > `.env` file > Defaults**.

Copy `.env.example` to `.env` in your project or home directory:

```bash
cp .env.example .env
```

Configure your preferred LLM provider:

```ini
# --- Default: Groq (Free & Ultra-Fast) ---
ANGRIST_LLM_BASE_URL=https://api.groq.com/openai/v1
ANGRIST_LLM_API_KEY=gsk_your_groq_api_key_here
ANGRIST_LLM_MODEL=llama-3.3-70b-versatile

# --- Preset: Local Ollama (Zero API Cost) ---
# ANGRIST_LLM_BASE_URL=http://localhost:11434/v1
# ANGRIST_LLM_API_KEY=
# ANGRIST_LLM_MODEL=qwen2.5-coder:7b

# --- Preset: Local vLLM ---
# ANGRIST_LLM_BASE_URL=http://localhost:8000/v1
# ANGRIST_LLM_API_KEY=none
# ANGRIST_LLM_MODEL=deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct

# --- Preset: OpenRouter / OpenAI ---
# ANGRIST_LLM_BASE_URL=https://openrouter.ai/api/v1
# ANGRIST_LLM_API_KEY=sk-or-...
# ANGRIST_LLM_MODEL=anthropic/claude-3.5-sonnet
```

---

## Quick Start

### 1. Fix a Class Method
Target a specific method inside a class, ensuring sibling methods and class attributes remain untouched:

```bash
angrist fix \
  --file demo/payment_processor.py \
  --target PaymentProcessor.settle_batch \
  --instruction "Fix fee deduction precedence and update transaction status" \
  --test-cmd "pytest demo/test_payment_processor.py"
```

### 2. Fix a Standalone Module Function
Target a top-level function directly:

```bash
angrist fix \
  --file requests/models.py \
  --target PreparedRequest.prepare_url \
  --instruction "Ensure query parameters with empty strings preserve key names"
```

### 3. Read Long Instructions from File
For complex bugs, traceback dumps, or issue descriptions:

```bash
angrist fix \
  --file flask/blueprints.py \
  --target Blueprint.add_url_rule \
  --instruction-file issue_description.txt
```

### 4. Automatic Safe Merge
Once the patch passes AST validation, lint gates, and regression test suites, merge it back into the base branch automatically (aborts if your working tree has uncommitted changes):

```bash
angrist fix \
  --file service/auth.py \
  --target authenticate_user \
  --instruction "Reject expired tokens" \
  --auto-merge
```

### 5. Run SWE-bench Benchmark Suite
Evaluate Angrist's accuracy and gating against real-world SWE-bench Lite bugs:

```bash
# Run the curated 10-instance benchmark suite
angrist benchmark

# Run against the official 300-instance manifest
angrist benchmark --dataset benchmarks/swe_bench/official_manifest.json --filter django
```

---

## Command-Line Interface

All commands support comprehensive options for terminal use and pipeline composition:

| Command | Description |
|---|---|
| `angrist fix --file <path> --target <name>` | Execute isolated, AST-constrained repair on a function or class method. |
| `angrist benchmark` | Run evaluation suite across SWE-bench Lite benchmark instances. |
| `angrist --help` | Display command-line options and usage flags. |

### Key Options for `angrist fix`:

| Option | Default | Description |
|---|---|---|
| `--file PATH` | Required | Relative path to the target Python source file. |
| `--target IDENT` | Required | Function name or `ClassName.method_name` to repair. |
| `--instruction TEXT` | Optional | Plain-text repair instruction or description of the bug. |
| `--instruction-file PATH` | Optional | Path to file containing repair instructions. |
| `--test-cmd CMD` | `"pytest"` | Test command to execute in the sandbox before and after patching. |
| `--lint-cmd CMD` | `"ruff check ."` | Linter command used to verify no new errors are introduced. |
| `--auto-merge` | `False` | Merge the verified branch into your current branch automatically. |
| `--max-retries INT` | `3` | Maximum LLM regeneration attempts on AST or test gate failure. |

---

## Architecture

Angrist uses a strictly decoupled, unidirectional pipeline:

```
Python Source File & Target Identifier
    │
    ▼
[ angrist.ast_guard ]     Tree-sitter AST coordinate locking (preserves all sibling code)
    │
    ▼
[ angrist.sandbox ]       Isolated Git worktree creation & baseline test/lint check
    │
    ▼
[ angrist.patcher ]       Model-agnostic prompt synthesis & syntactic output sanitization
    │
    ▼
[ angrist.gate ]          AST scope invariance check, delta test run & lint comparison
    │
    ▼
[ angrist.merge ]         Atomic branch merge or immediate rollback on failure
```

---

## Benchmarks

### SWE-bench Lite (Curated 10-Instance Diverse Suite)

Evaluated live against `openai/gpt-oss-120b` via Groq across 10 real-world bug instances from 7 major open-source repositories:

| Instance ID | Repository | Target Function | Status | AST Scope | Regressions | Duration |
|---|---|---|:---:|:---:|:---:|:---:|
| `psf__requests-1142` | `psf/requests` | `PreparedRequest.prepare_url` | **PASS** | 100% Locked | 0 | 2.52s |
| `marshmallow__marshmallow-1343` | `marshmallow` | `Schema._do_load` | **PASS** | 100% Locked | 0 | 2.50s |
| `pallets__flask-4045` | `pallets/flask` | `Blueprint.add_url_rule` | **PASS** | 100% Locked | 0 | 2.52s |
| `django__django-11099` | `django/django` | `ASCIIUsernameValidator.__init__` | **PASS** | 100% Locked | 0 | 2.15s |
| `pallets__flask-4992` | `pallets/flask` | `Config.from_file` | **PASS** | 100% Locked | 0 | 3.16s |
| `pylint-dev__pylint-5859` | `pylint-dev/pylint` | `EncodingChecker.open` | **PASS** | 100% Locked | 0 | 2.04s |
| `pytest-dev__pytest-11148` | `pytest-dev/pytest` | `import_path` | **FAIL** | 100% Locked | 0 | 4.72s |
| `django__django-11049` | `django/django` | `DurationField.get_error_message` | **FAIL** | 100% Locked | 0 | 2.94s |
| `sphinx-doc__sphinx-10325` | `sphinx-doc/sphinx` | `inherited_members_option` | **PASS** | 100% Locked | 0 | 3.29s |
| `psf__requests-1963` | `psf/requests` | `SessionRedirect.resolve_redirect_method` | **PASS** | 100% Locked | 0 | 2.58s |

### Benchmark Insights:
- **80.0% Pass Rate (8/10):** 8 of 10 real-world open-source bugs resolved on the first attempt (Total duration: 29.56s).
- **Conservative Gate Safety:** The 2 incomplete candidate patches were rejected cleanly by the delta test gate, preventing any repository contamination.
- **100% Target Containment:** Across all 10 instances, zero lines outside the target function or method were modified.
- **Zero Worktree Leaks:** 100% of temporary worktrees and branches were systematically cleaned up.
- **Official SWE-bench Lite Integration:** Angrist includes the complete 300-instance manifest (`benchmarks/swe_bench/official_manifest.json`) directly scraped from Princeton NLP Hugging Face, verifying that 297 of 300 instances (99%) in SWE-bench Lite are single-function targets suited for Angrist.

### Failure Case Root-Cause Analysis:
Transparency regarding the 2 rejected candidates illustrates how Angrist's conservative gating protects codebases:

1. **`pytest-dev__pytest-11148` (`_pytest.pathlib.import_path`):**
   - **Target Behavior:** Check `sys.modules` cache before importing a module to prevent duplicate imports under `import-mode=importlib`.
   - **Failure Reason:** The model over-engineered the fix by synthesizing a full `importlib.util.spec_from_file_location` loader instead of checking the cache dictionary. Because the test used a virtual path that does not exist physically on disk, `spec.loader` evaluated to `None` and raised `ImportError`. The patch also re-imported `sys` inside the body, which was caught by the Lint Gate as a duplicate import (`F811`).
   - **Gate Outcome:** Both test and lint gates rejected the patch. The active branch remained untouched.

2. **`django__django-11049` (`DurationField.get_error_message`):**
   - **Target Behavior:** Correct format typo `[DD] [HH:[MM:]]ss` to `[DD] [[HH:]MM:]ss`.
   - **Failure Reason:** On the initial run, the model used a string `.replace()` strategy that left remnants of the original format in the string, failing the negative assertion `assert "[DD] [HH:[MM:]]ss[.uuuuuu] format." not in msg` (partial fix).
   - **Gate Outcome:** The test delta gate accurately detected that the failure condition persisted, safely aborting the candidate merge.

To reproduce the benchmark:

```bash
# Run the curated 10-instance benchmark suite
angrist benchmark

# Run against the official 300-instance manifest
angrist benchmark --dataset benchmarks/swe_bench/official_manifest.json --filter django
```

---

## Capabilities, Scope & Known Limitations

### What Angrist Does Best
- **Logic & Boundary Bugs:** Fix off-by-one errors, unhandled exceptions, query string parsing, regex edge cases, and missing type casts.
- **Strict Scope Invariant:** Guaranteed preservation of entire file layout, comments, docstrings, and sibling classes.
- **Zero Workspace Contamination:** You can run Angrist in the middle of editing another feature; your uncommitted work is untouched.

### Known Boundaries
1. **Single-Function Scope:** Angrist is deliberately designed for single-node repairs. It will not execute cross-file refactors or architectural migrations.
2. **Top-Level Import Injection:** The AST scope guard rejects LLM responses that add imports at the module top-level to prevent namespace pollution. Imports required by the fix must be placed inside the function body or already exist in the module.
3. **Target Must Exist:** The target function or method must parse cleanly via Tree-sitter before the repair can begin.

---

## Supported Platforms

- **Linux (x86_64 / ARM64):** Fully supported.
- **macOS (Apple Silicon M-series / Intel):** Fully supported.
- **Windows (x86_64):** Fully supported (custom `onexc` read-only `.git` handling).

---

## Roadmap & Milestones

- [x] **v0.1.0 (Core Engine):** Tree-sitter AST guard, Git-worktree sandbox isolation, and LLM patcher.
- [x] **AST Robustness:** Decorated definitions, nested classes, structural occurrence indexing, and deletion guards.
- [x] **Conservative Delta Gating:** Multi-format JSON/concise lint parsing and comprehensive `FAILED`/`ERROR` test regression detection.
- [x] **Configuration & Benchmark Suite:** `.env` resolver, CLI overrides, and integrated SWE-bench runner with Rich UI.
- [ ] **Multi-Language AST Support:** Expanding Tree-sitter AST guards to TypeScript/JavaScript and Go.
- [ ] **Interactive TUI Diff Viewer:** In-terminal side-by-side AST diff inspector before merging.

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code style guidelines, and pull request workflows.

Please also read and adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Security

To report security issues or vulnerabilities, please review our [Security Policy](SECURITY.md).

---

## License

MIT License. See [LICENSE](LICENSE) for details.
