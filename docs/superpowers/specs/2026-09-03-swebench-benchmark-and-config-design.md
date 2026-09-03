# angrist — SWE-bench Benchmark Suite & Enhanced Configuration Design Spec

## Problem

`angrist` provides deterministic git-worktree isolation and AST-scope-locked LLM patching for Python micro-fixes. However:
1. **Lack of standardized benchmark evaluation**: There is no objective, rigorous benchmark to measure `angrist`'s accuracy, scope violation defense rate, and retry efficiency against real-world open-source bugs.
2. **Missing developer configuration ergonomics**: Model parameters and API keys are read solely from raw `os.environ` without `.env` auto-loading, CLI override flags (`--model`, `--api-key`, `--base-url`), or starter `.env.example` templates.
3. **Need for compelling visual demonstration**: Benchmark and micro-fix runs need polished, aesthetically pleasant terminal UI/UX and automated VHS tape recording scripts for demonstrations and presentations.

## Goals

1. **Flexible Configuration Hierarchy**: Support `.env` files, environment variables, and CLI flags with clear priority order.
2. **Curated SWE-bench Suite**: Bundle a representative, verifiable subset of single-function bug instances from SWE-bench Lite (e.g. `psf/requests`, `pallets/flask`, `marshmallow`, `pytest-dev/pytest`).
3. **Integrated Benchmark CLI**: Provide `angrist benchmark [OPTIONS]` command to batch-run instances, record metrics, and export JSON summaries.
4. **Delightful Terminal UI/UX**: Use modern, accessible color schemes (emerald green for pass, amber for caught violations/retries, rose red for regression, slate gray for timing) with rounded Rich panels and tables.
5. **Automated VHS Recording**: Provide clean, validated `.tape` scripts configured with modern terminal themes (`Catppuccin Mocha`, rounded window borders) for crisp GIF recordings.

## Architecture

```
User / Evaluator (angrist benchmark --dataset benchmarks/swe_bench)
         |
         v
[Configuration Resolver]  .env -> env vars -> CLI flags (highest priority)
         |
         v
[Benchmark Runner]  Loads manifest.json, iterates over test instances
         |
         +--> Per Instance:
         |      1. Snapshot check & baseline test verification
         |      2. Run angrist core engine: run_fix(...)
         |      3. Measure: Pass@1, Scope Violations caught, Sanitization errors, Retries, Latency
         |
         v
[UI/UX Presenter]
  - Rich Live Progress / Spinner
  - High-Contrast Modern Results Table (Catppuccin / Tailwind Palette)
  - Aggregate Summary Panel
         |
         v
[Exporter]  Writes benchmark_results.json
```

## Detailed Specifications

### 1. Configuration System

Priority hierarchy (highest to lowest):
1. **CLI Flags**: `--model`, `--api-key`, `--base-url`
2. **Environment Variables**: `ANGRIST_LLM_MODEL`, `ANGRIST_LLM_API_KEY`, `ANGRIST_LLM_BASE_URL`
3. **`.env` File**: Automatically loaded from current working directory if present (via `python-dotenv`).
4. **Default Fallbacks**:
   - `model`: `"gpt-oss"` (or specified model)
   - `base_url`: `"https://api.groq.com/openai/v1"`
   - `api_key`: `""` (when empty, `Authorization` header is omitted, enabling authless local servers like Ollama/vLLM).

Provide `.env.example` at repository root with presets for Groq, local Ollama, local vLLM, and OpenAI/OpenRouter.

### 2. SWE-bench Benchmark Suite

Directory structure:
```
benchmarks/
  swe_bench/
    manifest.json
    instances/
      psf__requests-1142/
        problem_statement.txt
        repo/ ...
      pallets__flask-4045/
        problem_statement.txt
        repo/ ...
      marshmallow__marshmallow-1343/
        problem_statement.txt
        repo/ ...
```

Each instance in `manifest.json` defines:
- `instance_id` (str): e.g. `"psf__requests-1142"`
- `repo` (str): e.g. `"psf/requests"`
- `file` (str): Relative path to target file
- `target` (str): Qualified target function or method
- `instruction_file` (str): Relative path to issue description
- `test_cmd` (str): Specific test command targeting the bug
- `category` (str): Bug category tag

### 3. CLI Commands & Options

#### Updated `angrist fix`:
```bash
angrist fix --file <path> --target <qualifier> [OPTIONS]
  --instruction / --instruction-file
  --model <str>
  --api-key <str>
  --base-url <str>
  --test-cmd <str>      [default: pytest]
  --lint-cmd <str>      [default: ruff check]
  --auto-merge          [default: no-auto-merge]
```

#### New `angrist benchmark`:
```bash
angrist benchmark [OPTIONS]
  --dataset <path>      [default: benchmarks/swe_bench]
  --filter <str>        Regex/string filter for instance_id or repo
  --output-json <path>  [default: benchmark_results.json]
  --model <str>
  --api-key <str>
  --base-url <str>
  --max-retries <int>   [default: 3]
```

### 4. UI/UX Design & Styling

Terminal design guidelines:
- **Rounded Box Borders**: `box.ROUNDED` for panels and tables.
- **Palette Tokens**:
  - `SUCCESS`: `bold #10b981` (Emerald Green)
  - `WARNING`: `bold #f59e0b` (Warm Amber - used for caught scope violations and retries)
  - `DANGER`: `bold #f43f5e` (Rose Red - used for regressed / failed instances)
  - `ACCENT`: `bold #06b6d4` (Cyan - instance IDs and headers)
  - `MUTED`: `dim #94a3b8` (Slate Gray - timing and secondary labels)
- **Summary Panel**:
  Displays a highlighted card with:
  - Total Instances & Resolved Rate (percentage)
  - Scope Guard Interceptions (total violations prevented)
  - Average Retries to Success
  - Average Elapsed Time per Fix

### 5. Metrics & JSON Output Schema

`benchmark_results.json`:
```json
{
  "timestamp": "2026-09-03T07:45:00Z",
  "model": "llama-3.3-70b-versatile",
  "base_url": "https://api.groq.com/openai/v1",
  "summary": {
    "total": 3,
    "passed": 3,
    "failed": 0,
    "resolved_rate": 1.0,
    "total_scope_violations_blocked": 1,
    "average_retries": 1.33,
    "total_duration_seconds": 14.8
  },
  "instances": [
    {
      "instance_id": "psf__requests-1142",
      "target": "PreparedRequest.prepare_url",
      "status": "passed",
      "retries": 1,
      "scope_violations": 0,
      "sanitization_errors": 0,
      "duration_seconds": 4.2
    }
  ]
}
```

### 6. VHS Recording (`benchmark.tape`)

Configuration:
- `Output benchmark.gif`
- `Set Theme "Catppuccin Mocha"`
- `Set FontSize 15`
- `Set Width 1280`
- `Set Height 720`
- `Set WindowBar Colorful`
- Types and executes `angrist benchmark --dataset benchmarks/swe_bench`
- Renders rich visual output cleanly into `benchmark.gif`.
