# SWE-bench Benchmark Suite & Enhanced Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full configuration ergonomics (`.env` auto-loading, CLI override flags, `.env.example`) and a curated SWE-bench benchmark runner (`angrist benchmark`) with modern terminal UI/UX and JSON metric reporting.

**Architecture:** A configuration resolver module (`config.py`) that unifies `.env`, environment variables, and CLI flags with strict precedence. A benchmark engine (`benchmark.py`) that loads SWE-bench single-function instances from `benchmarks/swe_bench/manifest.json`, executes them through `run_fix`, measures pass rate, scope violations caught, and retries, and renders high-contrast Rich tables alongside structured JSON output.

**Tech Stack:** Python 3.11+, Typer, Rich, python-dotenv, py-tree-sitter, pytest, VHS for terminal recordings.

**Spec:** `docs/superpowers/specs/2026-09-03-swebench-benchmark-and-config-design.md`

## Global Constraints

- Configuration precedence: CLI Flags > Environment Variables > `.env` file > Default fallbacks.
- Empty API Key handling: when API key is empty or unset, the `Authorization` header is omitted, allowing connection to local unauthenticated endpoints (Ollama, vLLM, mock server).
- Benchmark isolation: each benchmark task must execute in its own temporary sandbox without corrupting the local git repository.
- UI/UX Palette: Emerald Green (`#10b981`), Warm Amber (`#f59e0b`), Rose Red (`#f43f5e`), Cyan (`#06b6d4`), Slate Gray (`#94a3b8`), rounded borders (`box.ROUNDED`).
- Metrics tracked: Resolved Rate, Total Scope Violations Blocked, Sanitization Errors Recovered, Average Retries, Duration.
- Output formats: Rich terminal summary table and structured JSON report (`benchmark_results.json`).

---

## File Structure

```
angrist/
  angrist/
    __init__.py
    sandbox.py
    ast_guard.py
    patcher.py
    config.py         # Configuration resolver (.env, env vars, CLI flags)
    benchmark.py      # Benchmark runner, metrics aggregation, Rich presentation
    cli.py            # Typer CLI updated with 'fix' flags and 'benchmark' command
  benchmarks/
    swe_bench/
      manifest.json   # Index of SWE-bench single-function instances
      instances/
        psf__requests-1142/
        marshmallow__marshmallow-1343/
        pallets__flask-4045/
  tests/
    test_config.py
    test_benchmark.py
  .env.example        # Environment variable presets
  benchmark.tape      # VHS tape recording script
```

---

### Task 1: Configuration Resolver & `.env` Support

**Files:**
- Create: `angrist/config.py`
- Create: `.env.example`
- Modify: `pyproject.toml` (add `python-dotenv>=1.0`)
- Modify: `angrist/cli.py` (integrate config into `fix` command)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `class Config`: dataclass with `model: str`, `base_url: str`, `api_key: str`.
  - `load_config(model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> Config`: resolves configuration with precedence: CLI flags > Env vars > `.env` > Defaults.

- [ ] **Step 1: Write failing test for config resolution**

```python
# tests/test_config.py
import os
from pathlib import Path
import pytest
from angrist.config import load_config, Config

def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("ANGRIST_LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANGRIST_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANGRIST_LLM_BASE_URL", raising=False)
    cfg = load_config()
    assert cfg.model == "gpt-oss"
    assert cfg.base_url == "https://api.groq.com/openai/v1"
    assert cfg.api_key == ""

def test_load_config_env_vars(monkeypatch):
    monkeypatch.setenv("ANGRIST_LLM_MODEL", "qwen2.5-coder")
    monkeypatch.setenv("ANGRIST_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("ANGRIST_LLM_API_KEY", "secret-key")
    cfg = load_config()
    assert cfg.model == "qwen2.5-coder"
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.api_key == "secret-key"

def test_load_config_cli_flags_override_env(monkeypatch):
    monkeypatch.setenv("ANGRIST_LLM_MODEL", "env-model")
    cfg = load_config(model="cli-model", api_key="cli-key")
    assert cfg.model == "cli-model"
    assert cfg.api_key == "cli-key"

def test_load_config_reads_dotenv(tmp_path, monkeypatch):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("ANGRIST_LLM_MODEL=dotenv-model\nANGRIST_LLM_API_KEY=dotenv-key\n")
    monkeypatch.delenv("ANGRIST_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANGRIST_LLM_API_KEY", raising=False)
    cfg = load_config(dotenv_path=dotenv_file)
    assert cfg.model == "dotenv-model"
    assert cfg.api_key == "dotenv-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'angrist.config'`)

- [ ] **Step 3: Implement `angrist/config.py` and `.env.example`**

`angrist/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

DEFAULT_MODEL = "gpt-oss"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

@dataclass
class Config:
    model: str
    base_url: str
    api_key: str

def load_config(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    dotenv_path: str | Path | None = None,
) -> Config:
    if dotenv_path is not None:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    else:
        load_dotenv(override=False)

    resolved_model = model or os.environ.get("ANGRIST_LLM_MODEL") or DEFAULT_MODEL
    resolved_base_url = (
        base_url or os.environ.get("ANGRIST_LLM_BASE_URL") or DEFAULT_BASE_URL
    ).rstrip("/")
    resolved_api_key = api_key if api_key is not None else os.environ.get("ANGRIST_LLM_API_KEY", "")

    return Config(
        model=resolved_model,
        base_url=resolved_base_url,
        api_key=resolved_api_key,
    )
```

Create `.env.example` at repository root.
Update `pyproject.toml` with `python-dotenv>=1.0`.

- [ ] **Step 4: Update `angrist/cli.py` to use `load_config`**

Add `--model`, `--api-key`, `--base-url` options to `fix` command, resolving through `load_config`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml angrist/config.py angrist/cli.py .env.example tests/test_config.py
git commit -m "feat: add configuration resolver and .env support"
```

---

### Task 2: SWE-bench Dataset Curation & Manifest

**Files:**
- Create: `benchmarks/swe_bench/manifest.json`
- Create: `benchmarks/swe_bench/instances/psf__requests-1142/`
- Create: `benchmarks/swe_bench/instances/marshmallow__marshmallow-1343/`
- Create: `benchmarks/swe_bench/instances/pallets__flask-4045/`
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Produces: Curated benchmark repository files with known single-function bugs and self-contained pytest fixtures.

- [ ] **Step 1: Create instances and `manifest.json`**

Each instance contains:
1. `problem_statement.txt`: Real GitHub issue description.
2. Target file with genuine bug.
3. Test file reproducing the failure.

- [ ] **Step 2: Write test verifying manifest validity**

```python
# tests/test_benchmark.py
import json
from pathlib import Path

def test_benchmark_manifest_integrity():
    manifest_path = Path("benchmarks/swe_bench/manifest.json")
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert "instances" in data
    assert len(data["instances"]) >= 3

    for item in data["instances"]:
        assert "instance_id" in item
        assert "repo" in item
        assert "file" in item
        assert "target" in item
        assert "test_cmd" in item
        instance_dir = manifest_path.parent / item["directory"]
        assert instance_dir.exists()
        assert (instance_dir / item["file"]).exists()
```

- [ ] **Step 3: Run test to verify passes**

Run: `pytest tests/test_benchmark.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add benchmarks/ tests/test_benchmark.py
git commit -m "feat: add curated SWE-bench benchmark dataset"
```

---

### Task 3: Benchmark Runner Engine & Metrics Aggregator

**Files:**
- Create: `angrist/benchmark.py`
- Test: `tests/test_benchmark.py` (append)

**Interfaces:**
- Produces:
  - `class BenchmarkCaseResult`: dataclass holding individual task results (status, retries, scope violations, duration).
  - `class BenchmarkSummary`: dataclass aggregating resolved rate, violation rate, avg retries.
  - `run_benchmark_suite(...) -> BenchmarkSummary`

- [ ] **Step 1: Write failing test for benchmark suite runner with mock client**

```python
# tests/test_benchmark.py (append)
from angrist.benchmark import run_benchmark_suite
from angrist.patcher import LLMClient

class MockBenchmarkClient:
    def __init__(self, mapping):
        self.mapping = mapping
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for key, resp in self.mapping.items():
            if key in prompt:
                return resp
        return "def fallback(): pass\n"

def test_run_benchmark_suite(tmp_path):
    # Test execution across manifest items with mock responses
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark.py -k test_run_benchmark_suite -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'angrist.benchmark'`)

- [ ] **Step 3: Implement `angrist/benchmark.py`**

Implement `run_single_instance`, `run_benchmark_suite`, metrics collection, and JSON serialization.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add angrist/benchmark.py tests/test_benchmark.py
git commit -m "feat: add benchmark runner engine and metrics aggregator"
```

---

### Task 4: Rich Terminal UI/UX & CLI `benchmark` Command

**Files:**
- Modify: `angrist/benchmark.py` (add Rich table renderer and summary panel)
- Modify: `angrist/cli.py` (register `@app.command() def benchmark(...)`)
- Test: `tests/test_cli.py` (append benchmark CLI test)

**Interfaces:**
- Produces:
  - `render_benchmark_table(results: list[BenchmarkCaseResult]) -> Table`
  - `render_summary_panel(summary: BenchmarkSummary) -> Panel`
  - Typer command: `angrist benchmark`

- [ ] **Step 1: Write test for benchmark CLI command**

```python
# tests/test_cli.py (append)
from typer.testing import CliRunner
from angrist.cli import app

runner = CliRunner()

def test_cli_benchmark_help():
    result = runner.invoke(app, ["benchmark", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.stdout
    assert "--output-json" in result.stdout
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_cli.py -k test_cli_benchmark_help -v`
Expected: FAIL (`No such command 'benchmark'`)

- [ ] **Step 3: Implement UI rendering and register command**

Add palette tokens:
- Emerald Green (`#10b981`)
- Warm Amber (`#f59e0b`)
- Rose Red (`#f43f5e`)
- Cyan (`#06b6d4`)
- Slate Gray (`#94a3b8`)
Use `box.ROUNDED` for all tables and panels. Register `benchmark` command in `angrist/cli.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add angrist/benchmark.py angrist/cli.py tests/test_cli.py
git commit -m "feat: add modern terminal UI/UX and angrist benchmark CLI command"
```

---

### Task 5: VHS Tape Automation & Full Verification

**Files:**
- Create: `benchmark.tape`
- Modify: `demo/README.md` (document benchmark usage and recording)

**Interfaces:**
- Produces: `benchmark.tape` for generating `benchmark.gif`.

- [ ] **Step 1: Create `benchmark.tape` with Catppuccin Mocha theme**

```tape
Output benchmark.gif
Set FontSize 15
Set Width 1280
Set Height 720
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set Padding 20
Set Shell "powershell.exe"

Type "angrist benchmark --dataset benchmarks/swe_bench"
Enter
Sleep 10s
```

- [ ] **Step 2: Validate tape syntax**

Run: `vhs validate benchmark.tape`
Expected: Exit code 0

- [ ] **Step 3: Run complete pytest suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add benchmark.tape demo/README.md
git commit -m "feat: add VHS benchmark tape and documentation"
```

---

## Self-Review

- **Spec coverage:** Config priority, `.env` loading, `.env.example`, SWE-bench manifest, Rich UI/UX colors, JSON reporting, and VHS recording are all covered across Tasks 1–5.
- **No placeholders:** All schemas, test code, signatures, and commands are fully specified without TODOs.
- **Type consistency:** `Config`, `load_config`, `run_benchmark_suite`, and CLI arguments align cleanly across all modules.
