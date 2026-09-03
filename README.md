# Angrist

> *"As Angrist carved the Silmaril from the Iron Crown of Morgoth: excise the flaw, preserve the tree."*

[![CI](https://github.com/flxhrdyn/angrist/actions/workflows/ci.yml/badge.svg)](https://github.com/flxhrdyn/angrist/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/angrist?color=blue&logo=pypi&logoColor=white)](https://pypi.org/project/angrist/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

Angrist repairs bugs in Python functions using LLMs while strictly locking edits to the target AST node. It tests every patch in an isolated Git worktree before touching your code, preventing unintended modifications across the rest of the file.

![Angrist Demo](demo/demo.gif)

*Simulated terminal session (rendered from a real `angrist fix` + `angrist benchmark` run's captured output), not a live screen recording. Benchmark numbers shown match the committed [`benchmark_results.json`](benchmark_results.json), but expect run-to-run variance (observed 60-90% across repeated runs) since the demo uses a free small LLM (see [demo/README.md](demo/README.md)).*

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
- Git 2.20+
- Tree-sitter & Tree-sitter Python

---

## Configuration

Angrist resolves configuration in order: **CLI Flags > Environment Variables > `.env` file > Defaults**.

Copy `.env.example` to `.env` and set your provider credentials:

```ini
# --- Default: Groq (Free & Fast) ---
ANGRIST_LLM_BASE_URL=https://api.groq.com/openai/v1
ANGRIST_LLM_API_KEY=gsk_your_groq_api_key_here
ANGRIST_LLM_MODEL=llama-3.3-70b-versatile

# --- Preset: Local Ollama ---
# ANGRIST_LLM_BASE_URL=http://localhost:11434/v1
# ANGRIST_LLM_MODEL=qwen2.5-coder:7b

# --- Preset: Local vLLM ---
# ANGRIST_LLM_BASE_URL=http://localhost:8000/v1
# ANGRIST_LLM_MODEL=deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct
```

---

## Quick Start

### 1. Fix a Method or Function
Target a specific class method or top-level function without affecting surrounding code:

```bash
angrist fix \
  --file demo/payment_processor.py \
  --target PaymentProcessor.settle_batch \
  --instruction "Fix fee deduction precedence and update transaction status" \
  --test-cmd "pytest demo/test_payment_processor.py"
```

### 2. Automatic Safe Merge
Merge the verified patch into your current branch once all AST, lint, and test gates pass:

```bash
angrist fix \
  --file service/auth.py \
  --target authenticate_user \
  --instruction "Reject expired tokens" \
  --auto-merge
```

### 3. Run SWE-bench Lite Benchmark
Evaluate Angrist against 10 real-world open-source bug instances:

```bash
angrist benchmark
```

---

## Command-Line Options

| Option | Default | Description |
|---|---|---|
| `--file PATH` | Required | Relative path to target Python file. |
| `--target IDENT` | Required | Target name (`function_name` or `ClassName.method_name`). |
| `--instruction TEXT` | Optional | Plain-text repair instructions or bug description. |
| `--instruction-file PATH` | Optional | File path containing repair instructions. |
| `--test-cmd CMD` | `"pytest"` | Test command to run before and after patching. |
| `--lint-cmd CMD` | `"ruff check ."` | Linter command used to verify no regressions. |
| `--auto-merge` | `False` | Merge verified patch into current branch automatically. |
| `--max-retries INT` | `3` | Maximum LLM regeneration attempts on gate failure. |

---

## Architecture

Angrist uses a unidirectional, decoupled pipeline:

```
Python File & Target
    │
    ▼
[ ast_guard ]   Tree-sitter AST coordinate lock (preserves all sibling code)
    │
    ▼
[ sandbox ]     Isolated Git worktree creation & baseline verification
    │
    ▼
[ patcher ]     Model-agnostic prompt synthesis & syntactic sanitization
    │
    ▼
[ gate ]        AST invariance check, delta test run & lint comparison
    │
    ▼
[ merge ]       Atomic branch merge or immediate rollback on failure
```

---

## Benchmarks

### SWE-bench Lite (10-Instance Curated Suite)

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
- **80.0% Pass Rate (8/10):** 8 of 10 real-world bugs resolved on the first attempt (Total duration: 29.56s).
- **Gate Safety:** 2 incomplete candidate patches were rejected cleanly by the delta test gate, preventing workspace pollution.
- **Full 300-Instance Manifest:** All 300 instances from `princeton-nlp/SWE-bench_Lite` are indexed in `benchmarks/swe_bench/official_manifest.json` (297/300 verified single-function targets).

### Failure Case Root-Cause Analysis:
- **`pytest-dev__pytest-11148` (`import_path`):** The model over-engineered the fix by synthesizing a full `importlib` file loader instead of reading `sys.modules`, raising an `ImportError` on a virtual path. The patch was safely rejected by test and lint gates.
- **`django__django-11049` (`DurationField.get_error_message`):** On the first attempt, string replacement left remnants of the old format string, failing the negative assertion. The delta gate caught the incomplete fix and aborted the merge.

---

## Scope & Boundaries

- **Supported:** Logic bugs, boundary conditions, query string parsing, regex repairs, type coercion, and single-function fixes with full layout and comment preservation.
- **Out of Scope:** Multi-file refactors, architecture migrations, and module-level import injections. The target function must already exist and parse cleanly.

---

## Supported Platforms

- **Linux (x86_64 / ARM64)**: Fully supported.
- **macOS (Apple Silicon / Intel)**: Fully supported.
- **Windows (x86_64)**: Fully supported with atomic `onexc` read-only Git metadata handling.

---

## Roadmap

- [x] **Core Engine:** Tree-sitter AST guard, Git-worktree sandbox isolation, and LLM patcher.
- [x] **Delta Gating:** Multi-format JSON/concise lint parsing and test regression detection.
- [x] **SWE-bench Suite:** Integrated benchmark runner with Rich terminal output.
- [ ] **Multi-Language AST:** Expanding Tree-sitter guards to TypeScript and Go.
- [ ] **Interactive TUI:** In-terminal side-by-side AST diff inspector before merging.

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and review our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Security

To report security issues, please review our [Security Policy](SECURITY.md).

---

## License

MIT License. See [LICENSE](LICENSE) for details.
