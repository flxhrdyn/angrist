## Description

Brief summary of the change and the problem it solves.

## Type of Change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Benchmark update

## Core Invariant Verification

- [ ] AST scope lock is maintained (no edits outside target node).
- [ ] Ephemeral worktree isolation is preserved.
- [ ] Conservative test and lint delta gates remain intact.
- [ ] Filesystem cleanup handles Windows read-only flags properly.

## Testing & Quality

- [ ] Ran `pytest tests/ -v` (all tests passing).
- [ ] Ran `ruff check .` (zero lint/style warnings).
- [ ] Added regression or unit tests covering new logic.
