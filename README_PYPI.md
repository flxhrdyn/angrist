# Angrist

> *"As Angrist carved the Silmaril from the Iron Crown of Morgoth: excise the flaw, preserve the tree."*

A micro-agent CLI and Python library for targeted Python bug repairs using LLMs. Constrains every model edit to a single AST node and validates each patch in an isolated Git worktree before it touches your codebase.

[![CI](https://github.com/flxhrdyn/angrist/actions/workflows/ci.yml/badge.svg)](https://github.com/flxhrdyn/angrist/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/angrist?color=blue&logo=pypi&logoColor=white)](https://pypi.org/project/angrist/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

## Key Highlights

**Hard AST Scope Lock:** Tree-sitter parses the file and extracts only the target function or method. When the model returns a patch, Angrist byte-level verifies that every character outside the target node is identical to the original.

**Git Worktree Isolation:** Patches are applied, tested, and linted inside a throwaway Git worktree. Your working tree and uncommitted changes are never modified, and the sandbox is destroyed on exit.

**Delta Regression Gating:** A candidate patch must pass the full test suite and introduce zero new lint findings compared to the pre-patch baseline. Both gates are verified independently before any merge is allowed.

**Model Agnostic:** Connects to any OpenAI-compatible endpoint. Run locally with Ollama or vLLM using open-weights models, or connect to Groq and OpenAI without changing your workflow.

**Zero Infrastructure:** No daemon, no background service, no persistent process. Invoke it once per target and it exits cleanly.

## Installation

```bash
# Recommended via uv
uv tool install angrist

# Or via pipx
pipx install angrist

# Or standard pip
pip install angrist
```

**Requirements:** Python 3.11+, Git 2.20+

## Configuration

Angrist resolves credentials in order: **CLI flags > environment variables > `.env` file > defaults**.

Copy `.env.example` to `.env` and point it at your provider:

```ini
# Default: Groq (free and fast)
ANGRIST_LLM_BASE_URL=https://api.groq.com/openai/v1
ANGRIST_LLM_API_KEY=gsk_your_groq_api_key
ANGRIST_LLM_MODEL=llama-3.3-70b-versatile

# Local Ollama
# ANGRIST_LLM_BASE_URL=http://localhost:11434/v1
# ANGRIST_LLM_MODEL=qwen2.5-coder:7b

# Local vLLM
# ANGRIST_LLM_BASE_URL=http://localhost:8000/v1
# ANGRIST_LLM_MODEL=deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct
```

## Quickstart

### 1. Fix a Function or Method

Target a specific function or class method. Angrist extracts only that node, sends it to the model, applies the patch in a worktree, and runs your test suite before reporting the result:

```bash
angrist fix \
  --file src/payment_processor.py \
  --target PaymentProcessor.settle_batch \
  --instruction "Fix fee deduction precedence and update transaction status" \
  --test-cmd "pytest tests/test_payment_processor.py"
```

### 2. Automatic Safe Merge

Once all gates pass, merge the verified patch directly into your current branch:

```bash
angrist fix \
  --file src/auth.py \
  --target authenticate_user \
  --instruction "Reject tokens past their expiry timestamp" \
  --auto-merge
```

### 3. Run SWE-bench Lite Benchmark

Evaluate Angrist against 10 curated real-world bug instances from major open-source repositories:

```bash
angrist benchmark
```

### 4. Version and Help

```bash
angrist --version
angrist fix --help
python -m angrist --help
```

## Python API

```python
from angrist.cli import run_fix
from angrist.patcher import OpenAICompatibleClient

client = OpenAICompatibleClient(
    base_url="https://api.groq.com/openai/v1",
    api_key="gsk_...",
    model="llama-3.3-70b-versatile",
)

result = run_fix(
    file_path="src/payment_processor.py",
    target="PaymentProcessor.settle_batch",
    instruction="Fix fee deduction precedence and update transaction status",
    llm_client=client,
    test_cmd="pytest tests/test_payment_processor.py",
    lint_cmd="ruff check .",
    auto_merge=False,
)

if result["status"] == "success":
    print(f"Patch on branch: {result['branch']}")
    print(result["diff"])
else:
    print(f"Rejected: {result['reason']}")
```

## Capabilities and Known Limitations

**Supported targets:** Logic bugs, boundary conditions, off-by-one errors, type coercion, regex repairs, and any bug expressible as a single-function rewrite. Angrist preserves indentation, comments, and decorators exactly as written.

**Out of scope:** Multi-file refactors, cross-module import injections, and architecture-level changes. The target function must already exist and parse cleanly through Tree-sitter.

**Model quality dependency:** The patch quality is bounded by the model's ability to follow scope constraints. Strongly-scoped, single-task instructions produce better results than vague descriptions.

**Test command dependency:** Gates require a working baseline test command. If the baseline already fails, Angrist aborts before invoking the model.

## Benchmark Results

Evaluated against `openai/gpt-oss-120b` via Groq across 10 real-world bug instances from SWE-bench Lite:

| Instance | Target | Status | Duration |
|---|---|:---:|:---:|
| `psf__requests-1142` | `PreparedRequest.prepare_url` | PASS | 2.52s |
| `marshmallow__marshmallow-1343` | `Schema._do_load` | PASS | 2.50s |
| `pallets__flask-4045` | `Blueprint.add_url_rule` | PASS | 2.52s |
| `django__django-11099` | `ASCIIUsernameValidator` | PASS | 2.15s |
| `pallets__flask-4992` | `Config.from_file` | PASS | 3.16s |
| `pylint-dev__pylint-5859` | `EncodingChecker.open` | PASS | 2.04s |
| `pytest-dev__pytest-11148` | `import_path` | FAIL | 4.72s |
| `django__django-11049` | `DurationField.get_error_message` | FAIL | 2.94s |
| `sphinx-doc__sphinx-10325` | `inherited_members_option` | PASS | 3.29s |
| `psf__requests-1963` | `SessionRedirect.resolve_redirect_method` | PASS | 2.58s |

**80.0% pass rate (8/10).** Both failures were cleanly rejected by the delta test gate before reaching the merge step.

## Resources and Links

GitHub Repository: https://github.com/flxhrdyn/angrist

Demo Script: https://github.com/flxhrdyn/angrist/blob/main/demo/README.md

SWE-bench Benchmark Instances: https://github.com/flxhrdyn/angrist/tree/main/benchmarks/swe_bench

License: MIT License
