# Angrist Roadmap

This document outlines the product roadmap, architectural milestones, and planned capabilities for Angrist.

---

## Completed Milestones

### v0.1.0: Core Single-Function AST Micro-Agent
- [x] Tree-sitter AST scope guard targeting top-level functions and class methods.
- [x] Ephemeral Git worktree sandbox isolation with clean process isolation.
- [x] LLM patcher supporting OpenAI-compatible providers (Groq, Ollama, vLLM, OpenRouter).
- [x] Indentation-aware output sanitizer and code fence stripper.
- [x] CLI entrypoint `angrist fix` with basic error handling.

### v0.1.1: AST Hardening & Precision Review
- [x] Inner definition unnesting for decorated functions and properties (`@property`, `@staticmethod`, `@dataclass`).
- [x] Structural occurrence-based indexing replacing fragile byte offsets to prevent false violations on trailing code.
- [x] Nested class method resolution via hierarchical dot-separated targets (e.g. `OuterClass.InnerClass.method`).
- [x] Target deletion and rename rejection: ensures target node exists and retains identity in candidate AST.
- [x] Windows-safe `onexc` filesystem cleanup for read-only Git metadata.

### v0.2.0: Multi-Format Gating & SWE-bench Suite
- [x] Set-based lint delta gate supporting both JSON output (`ruff check --output-format=json`) and concise text formats (`flake8`, `mypy`, `pylint`).
- [x] Conservative test delta gate catching test-to-error conversions and distinguishing partial fixes from regressions.
- [x] Baseline test and lint pre-flight verification to avoid wasting LLM inference on broken environments.
- [x] Environment variable and `.env` configuration resolver with CLI flag overrides.
- [x] Curated SWE-bench Lite benchmark suite with automated metrics aggregation.
- [x] Modern Rich terminal interface with high-contrast result tables and evaluation panels.

---

## Near-Term Milestones (v0.3.x)

### v0.3.0: Interactive Terminal TUI & Side-by-Side Diff Inspection
- [ ] Interactive terminal mode allowing interactive selection of target functions using a syntax-highlighted code picker.
- [ ] Side-by-side terminal AST diff inspector showing exactly what changed inside the function body before committing or auto-merging.
- [ ] Prompt refinement prompt: interactive retry with user-provided hints when an initial patch fails regression tests.

### v0.3.1: Expanded Benchmark Coverage
- [ ] Expand curated SWE-bench instances to 20 real-world benchmark cases across diverse domains (network, parsing, ORM, algorithms).
- [ ] Support automated Docker-isolated test execution for dependencies requiring system-level C-extensions.

---

## Mid-Term Milestones (v0.4.x - v0.5.x)

### v0.4.0: Polyglot AST Guard (TypeScript / JavaScript & Go)
- [ ] Tree-sitter TypeScript and JavaScript grammar integration for targeted fixes in frontend/Node.js projects.
- [ ] Tree-sitter Go grammar integration for targeted Go function and method fixes.
- [ ] Language-agnostic test and lint adapter configurations (`npm test`, `vitest`, `eslint`, `go test`, `golangci-lint`).

### v0.5.0: CI/CD GitHub Action & Bot Integration
- [ ] Official `angrist-action` for GitHub Actions to automatically attempt repairs on failing PR test suites.
- [ ] Pull Request comment integration: reply to test failure reports with verified surgical patches on isolated branches.

---

## Long-Term Vision (v1.0.0+)

### v1.0.0: Autonomous Local Code Maintenance
- [ ] Continuous codebase invariant monitor: monitors repository health and surfaces one-click verified micro-fixes for linting and security warnings.
- [ ] Local model fine-tuning recipes optimized specifically for single-node code repair with 100% AST compliance.
