# Angrist 🎯

> **Git-worktree isolated, AST-scope-locked micro-agent for precise single-function code fixes.**

Angrist is a targeted, high-precision code repair tool designed to safely fix single functions or methods using LLMs without code drift, out-of-scope modifications, or repository corruption.

---

## Key Invariants

1. **AST-Scope Locked**: Powered by Tree-sitter, edits are mathematically constrained to exactly the targeted function or method body. Unrelated functions, class definitions, imports, or attributes cannot be modified.
2. **Git-Worktree Isolated**: All candidate patches, test suites, and linter runs execute in temporary, disposable Git worktrees. Your active workspace and branch remain 100% clean and untouched.
3. **Conservative Delta Gating**:
   - **Test Gate**: Distinguishes between preexisting failures and newly introduced regressions (`FAILED` and `ERROR`). Partial fixes are reported accurately.
   - **Lint Gate**: Multi-format set-based comparator (JSON & concise text) immune to line-number shifts.
4. **Resilient Cleanup**: Uses Python 3.12+ `onexc` handlers to safely clean up read-only Git metadata on Windows without leaving lingering directories.

---

## Quickstart

### 1. Installation

```bash
git clone https://github.com/username/angrist.git
cd angrist
pip install -e ".[dev]"
```

### 2. Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Set your preferred provider:

```ini
# Default: Groq (Free Tier)
ANGRIST_LLM_BASE_URL=https://api.groq.com/openai/v1
ANGRIST_LLM_API_KEY=gsk_your_groq_api_key_here
ANGRIST_LLM_MODEL=llama-3.3-70b-versatile

# Or Local Ollama / vLLM:
# ANGRIST_LLM_BASE_URL=http://localhost:11434/v1
# ANGRIST_LLM_API_KEY=
# ANGRIST_LLM_MODEL=qwen2.5-coder:7b
```

Configuration precedence: **CLI flags (`--model`, `--api-key`, `--base-url`) > Environment Variables > `.env` file > Built-in Defaults**.

---

## Usage

### 1. Fixing a Bug (`angrist fix`)

```bash
angrist fix \
  --file path/to/module.py \
  --target function_name \
  --instruction "Fix the ZeroDivisionError when denominator is zero"
```

For class methods:
```bash
angrist fix \
  --file path/to/module.py \
  --target ClassName.method_name \
  --instruction "Strip trailing slashes from path"
```

Options:
- `--instruction-file <path>`: Read complex instructions from a markdown or text file.
- `--model <name>`: Override model.
- `--test-cmd <cmd>`: Custom test command (default: `pytest`).
- `--lint-cmd <cmd>`: Custom lint command (default: `ruff check`).
- `--auto-merge`: Automatically merge the fix branch into the base branch on success (guarded against dirty working tree).

### 2. Evaluating on SWE-bench (`angrist benchmark`)

Angrist includes a curated benchmark suite featuring real-world instances from `SWE-bench Lite` (e.g. `requests`, `marshmallow`, `flask`).

```bash
angrist benchmark
```

Filter by repository or instance:
```bash
angrist benchmark --filter requests
```

Output format:
- **Terminal UI**: High-contrast, rounded Rich table with status badges (`PASS` in Emerald Green, `FAIL` in Rose Red) and evaluation summary panel.
- **Machine-readable JSON**: Saved to `benchmark_results.json` containing total counts, pass rates, durations, and per-instance execution logs.

---

## Testing & Quality

Run all 74 unit, integration, and benchmark tests:
```bash
pytest tests/ -v
```

Lint with Ruff:
```bash
ruff check .
```
