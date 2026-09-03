# Contributing to Angrist

Thank you for your interest in contributing to Angrist. As an open-source project dedicated to safe, mathematically constrained code repair, we hold ourselves to rigorous standards of software correctness, security, and reproducibility.

This guide outlines our development setup, testing practices, code quality guidelines, and pull request workflows.

---

## Code of Conduct

All contributors and maintainers are expected to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before participating.

---

## Development Setup

### Prerequisites
- Python 3.11 or higher
- Git 2.20 or higher
- `uv` (recommended) or `pip`

### Initializing the Workspace

Clone the repository and install the development dependencies:

```bash
git clone https://github.com/flxhrdyn/angrist.git
cd angrist

# Using uv (recommended)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Or using pip
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify your installation by running the test suite:

```bash
pytest tests/ -v
```

All tests should pass cleanly.

---

## Core Invariants to Respect

When contributing code changes to Angrist, keep its foundational architectural invariants in mind:

1. **AST-Scope Locked:** Code repairs must never modify anything outside the designated target node. The Tree-sitter AST guard in `angrist/ast_guard.py` is the security core of the application. Any changes to the AST guard must preserve occurrence-based structural indexing and reject deletions or renames.
2. **Ephemeral Worktree Isolation:** Operations that execute candidate patches, unit tests, or linters must run in isolated Git worktrees via `angrist/sandbox.py`. The user's active branch and working directory must never be modified directly during candidate verification.
3. **Conservative Delta Gating:** Gating logic must never silently pass a failing candidate. A patch that turns a test failure into an import or collection error must be rejected. Linter findings must be compared as rule signatures, not line counts.
4. **Clean Filesystem Cleanup:** All temporary resources must be purged on failure or exit. Windows file-lock handling using `onexc` handlers must be preserved.

---

## Development Workflow

### 1. Branching Strategy
- Create feature or fix branches from `main`.
- Use descriptive branch names: `feat/interactive-tui`, `fix/ast-decorator-unpacking`, `docs/architecture-guide`.

### 2. Code Quality & Linting
Angrist uses Ruff for linting and formatting. Run the linter locally before pushing:

```bash
# Check code style and rules
ruff check .

# Auto-fix formatting and imports
ruff check --fix .
```

Ensure all code follows these conventions:
- Strict type annotations on all public functions, classes, and methods.
- Comprehensive docstrings explaining non-obvious invariants and design decisions.
- Zero unused imports or unnecessary dependencies.
- No emojis or em-dashes in documentation and user-facing messages.

### 3. Writing Tests
We adhere strictly to Test-Driven Development (TDD):
- Every bug fix must include a regression test demonstrating the failure before the fix and success after.
- Every new feature must include unit tests and, if applicable, CLI integration tests.
- Tests should execute deterministically and clean up any temporary directories or Git worktrees.

Run the test suite:
```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_ast_guard.py -v

# Run with keyword filtering
pytest tests/ -k "lint_gate"
```

### 4. Commit Message Guidelines
We follow the Conventional Commits specification:

```text
feat(scope): add new capability
fix(scope): resolve issue or regression
docs(scope): update documentation
test(scope): add or modify test coverage
refactor(scope): code structure change without behavioral alteration
```

Examples:
- `feat(benchmark): add automated pass rate metrics aggregation`
- `fix(cli): parse json and concise lint output without line drift`
- `docs: update quickstart guide and architecture diagram`

---

## Submitting a Pull Request

1. Push your branch to your fork:
   ```bash
   git push origin feat/your-feature
   ```
2. Open a Pull Request against the `main` branch.
3. Provide a clear summary in the PR description:
   - What changed and why.
   - Any architectural implications or altered invariants.
   - Verification evidence (output of `pytest tests/` and `ruff check .`).
4. Ensure all automated CI checks pass.
5. Address any code review feedback respectfully and rigorously.
