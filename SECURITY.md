# Security Policy

Angrist executes code repair in local environments, manages Git worktrees, and interfaces with language models. We take security and repository integrity seriously.

---

## Supported Versions

Security updates and patches are actively applied to the following versions:

| Version | Supported |
|---|:---:|
| 0.1.x | Yes |
| < 0.1.0 | No |

---

## Reporting a Vulnerability

If you discover a potential security vulnerability in Angrist (such as an AST scope escape, unintended file execution, or command injection), please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please send an email to:
**security@angrist.org** (or contact the primary maintainer directly via GitHub Security Advisories).

Please include the following details in your report:
1. Description of the vulnerability and its potential impact.
2. Step-by-step reproduction instructions or a minimal proof-of-concept repository.
3. Your operating system and Python version.
4. Any proposed mitigations or patches, if available.

### What to Expect
- **Initial Response:** You will receive an acknowledgment of your report within 48 hours.
- **Triage & Assessment:** The maintainers will evaluate the vulnerability and determine severity.
- **Resolution & Release:** A fix will be developed, reviewed, and tested in a private branch before a public security release is published.
- **Credit:** We will publicly credit your contribution in release notes (unless you prefer to remain anonymous).

---

## Security Invariants

Angrist is designed with defense-in-depth principles:

1. **AST-Enforced Isolation:** Candidate patches cannot modify anything outside the target node. Top-level script executions, arbitrary module imports, and external file writes via the patch payload are blocked at the AST verification layer.
2. **Worktree Isolation:** Patches and tests execute inside disposable worktree sandboxes outside the main repository tree. An untrusted patch cannot inadvertently overwrite unstaged working changes in your active branch.
3. **No Automatic Shell Execution of Unsanitized Inputs:** File paths and target names are verified and sanitized before subprocess invocation.
