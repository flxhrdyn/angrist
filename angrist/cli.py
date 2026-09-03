from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import typer
from rich.console import Console

from angrist.ast_guard import (
    AmbiguousTargetError,
    ASTScopeViolationError,
    TargetNotFoundError,
    extract_node_source,
    validate_scope_source,
)
from angrist.patcher import (
    LLMClient,
    OpenAICompatibleClient,
    SanitizationError,
    apply_patch,
    build_patch_prompt,
    sanitize_output,
    target_indent,
)
from angrist.sandbox import WorktreeSandbox, current_branch

app = typer.Typer()
console = Console()


def _run(cmd: str, cwd: Path | str) -> subprocess.CompletedProcess:
    """Run a configured lint/test command using POSIX shell argument splitting.

    Prepends cwd to PYTHONPATH (H2) so local modules are importable in isolated worktrees.
    """
    args = shlex.split(cmd, posix=True)
    env = os.environ.copy()
    cwd_str = str(Path(cwd).resolve())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{cwd_str}{os.pathsep}{existing}" if existing else cwd_str

    return subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def _normalize_lint_cmd(cmd: str) -> str:
    """If using ruff check without explicit output format, request JSON (N6)."""
    args = shlex.split(cmd, posix=True)
    if (
        args
        and args[0] == "ruff"
        and "check" in args
        and not any(a.startswith("--output-format") for a in args)
    ):
        return f"{cmd} --output-format=json"
    return cmd


_CONCISE_LINT_RE = re.compile(
    r"^([^:\n]+):(?:\d+):(?:\d+:)?\s*([A-Za-z][A-Za-z0-9_-]+)\s*(.*)$"
)


def _parse_lint_findings(output: str) -> set[tuple[str, str]]:
    """Parse linter output into line-number-independent (filename, rule_code) signatures (N6).

    Supports JSON format (from ruff --output-format=json) and concise text format (flake8, mypy, etc.).
    Ignores non-matching human-readable context/syntax blocks.
    """
    # Try parsing as JSON first
    try:
        data = json.loads(output)
        if isinstance(data, list):
            findings = set()
            for item in data:
                if isinstance(item, dict):
                    fn = Path(item.get("filename", "")).name
                    code = item.get("code") or item.get("message", "")
                    findings.add((fn, str(code)))
            return findings
    except (json.JSONDecodeError, TypeError, ValueError):
        pass


    # Fallback to concise text parsing
    findings = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Found "):
            continue
        match = _CONCISE_LINT_RE.match(line)
        if match:
            file_part, code_part, _ = match.groups()
            findings.add((Path(file_part).name, code_part.strip()))
    return findings


def _check_lint_regression(
    baseline: subprocess.CompletedProcess, candidate: subprocess.CompletedProcess
) -> str | None:
    """Set-based delta gate for linting (N6).

    Passes if no new rule findings appear, comparing rule code signatures
    without being affected by line-number shifts.
    """
    if candidate.returncode == 0:
        return None
    if baseline.returncode == 0 and candidate.returncode != 0:
        return (
            "lint regressed (clean before the patch):\n"
            f"{candidate.stdout}\n{candidate.stderr}"
        )

    base_findings = _parse_lint_findings(baseline.stdout)
    cand_findings = _parse_lint_findings(candidate.stdout)

    if base_findings or cand_findings:
        new_findings = cand_findings - base_findings
        if new_findings:
            formatted = "\n".join(
                f"  - {f}: {rule}" if f else f"  - {rule}"
                for f, rule in sorted(new_findings)
            )
            return f"lint regressed: new finding(s) introduced after patch:\n{formatted}"
        return None

    if baseline.returncode != 0 and candidate.returncode != 0:
        return (
            f"lint command failed (exit code {candidate.returncode}):\n"
            f"{candidate.stdout}\n{candidate.stderr}"
        )
    return None


def _parse_failed_tests(output: str) -> set[str]:
    """Parse test failures and errors (N5: recognizes both FAILED and ERROR)."""
    failed = set()
    for line in output.splitlines():
        line = line.strip()
        if line.startswith(("FAILED ", "ERROR ")):
            parts = line.split()
            if len(parts) > 1:
                failed.add(parts[1])
    return failed


def _check_test_regression(
    baseline: subprocess.CompletedProcess, candidate: subprocess.CompletedProcess
) -> str | None:
    """Conservative delta gate for tests (N5, N9).

    Never silently passes if candidate exit code is non-zero.
    """
    if candidate.returncode == 0:
        return None

    base_failed = _parse_failed_tests(baseline.stdout)
    cand_failed = _parse_failed_tests(candidate.stdout)

    if base_failed or cand_failed:
        new_failures = cand_failed - base_failed
        if new_failures:
            return (
                f"tests regressed: {len(new_failures)} test/error(s) appeared after patch: "
                f"{', '.join(sorted(new_failures))}"
            )
        # N9 FIX: Accurate message when tests are still failing (e.g. partial fixes)
        if cand_failed:
            return (
                f"tests still failing after the patch ({len(cand_failed)} test(s) failed): "
                f"{', '.join(sorted(cand_failed))}"
            )

    # Candidate failed non-zero and could not be justified by baseline failures
    return (
        f"test runner failed (exit code {candidate.returncode}):\n"
        f"{candidate.stdout}\n{candidate.stderr}"
    )


def run_fix(
    file_path: str,
    target: str,
    instruction: str,
    llm_client: LLMClient,
    repo_path: str = ".",
    base_branch: str | None = None,
    test_cmd: str = "pytest",
    lint_cmd: str = "ruff check",
    auto_merge: bool = False,
    max_retries: int = 3,
) -> dict:
    repo_path = Path(repo_path)
    if base_branch is None:
        base_branch = current_branch(repo_path)

    # H4 FIX: Gracefully handle paths outside repository
    try:
        rel_file = Path(file_path).resolve().relative_to(repo_path.resolve())
    except ValueError:
        return {
            "status": "failed",
            "branch": None,
            "reason": f"File '{file_path}' is not within repository '{repo_path}'",
            "diff": None,
        }

    target_file = repo_path / rel_file

    if not target_file.exists():
        return {
            "status": "failed",
            "branch": None,
            "reason": f"No such file: {file_path}",
            "diff": None,
        }

    try:
        extract_node_source(target_file, target)
    except (TargetNotFoundError, AmbiguousTargetError) as e:
        return {"status": "failed", "branch": None, "reason": str(e), "diff": None}

    sandbox = WorktreeSandbox(base_branch=base_branch, repo_path=repo_path)

    try:
        with sandbox as wt_path:
            sandboxed_file = wt_path / rel_file
            original_source = sandboxed_file.read_text()

            effective_lint_cmd = _normalize_lint_cmd(lint_cmd)
            baseline_lint = _run(effective_lint_cmd, wt_path)
            baseline_test = _run(test_cmd, wt_path)

            # N8 FIX: Verify baseline lint command is valid
            if baseline_lint.returncode not in (0, 1) or (
                "error" in baseline_lint.stderr.lower() and not baseline_lint.stdout.strip()
            ):
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": None,
                    "reason": (
                        f"Baseline lint command failed with exit code {baseline_lint.returncode}. "
                        "Ensure the lint command and dependencies are valid:\n"
                        f"{baseline_lint.stderr or baseline_lint.stdout}"
                    ),
                    "diff": None,
                }

            # H2 FIX: Detect when baseline test runner fails due to environment/invocation error
            # pytest exit codes: 0 = pass, 1 = tests failed, 2 = interrupted, 3 = internal error, 4 = usage error, 5 = no tests collected
            if baseline_test.returncode not in (0, 1):
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": None,
                    "reason": (
                        f"Baseline test command failed with exit code {baseline_test.returncode} "
                        "before applying any patch. Ensure test dependencies and commands are valid:\n"
                        f"{baseline_test.stderr or baseline_test.stdout}"
                    ),
                    "diff": None,
                }

            indent_cols = target_indent(sandboxed_file, target)

            failure_detail = None
            patched = False
            for _ in range(1, max_retries + 1):
                target_source = extract_node_source(sandboxed_file, target)
                prompt = build_patch_prompt(target_source, instruction, failure_detail)
                raw = llm_client.complete(prompt)

                try:
                    clean = sanitize_output(raw, indent_cols)
                    apply_patch(sandboxed_file, target, clean)
                    validate_scope_source(
                        original_source, sandboxed_file.read_text(), target
                    )
                    patched = True
                    break
                except (SanitizationError, ASTScopeViolationError) as e:
                    failure_detail = str(e)
                    sandboxed_file.write_text(original_source)

            # H1 & N3 FIX: Clean up sandbox and return branch=None on failure
            if not patched:
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": None,
                    "reason": (
                        f"no in-scope patch after {max_retries} attempts; "
                        f"last rejection: {failure_detail}"
                    ),
                    "diff": None,
                }

            # N6 FIX: Set-based delta gate for linting
            lint_error = _check_lint_regression(baseline_lint, _run(effective_lint_cmd, wt_path))
            if lint_error:
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": None,
                    "reason": lint_error,
                    "diff": None,
                }

            # N5 & N9 FIX: Conservative delta gate for tests
            test_error = _check_test_regression(baseline_test, _run(test_cmd, wt_path))
            if test_error:
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": None,
                    "reason": test_error,
                    "diff": None,
                }

            diff = subprocess.run(
                ["git", "diff", base_branch],
                cwd=wt_path,
                capture_output=True,
                text=True,
                check=False,
            ).stdout

            subprocess.run(
                ["git", "add", "."], cwd=wt_path, check=True, capture_output=True, text=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"fix: {instruction}"],
                cwd=wt_path,
                check=True,
                capture_output=True,
                text=True,
            )

            branch_name = sandbox.branch_name

            # N1 FIX: Safe auto-merge without touching or forcibly moving user's branch
            if auto_merge:
                status_res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if status_res.stdout.strip():
                    return {
                        "status": "failed",
                        "branch": branch_name,
                        "reason": (
                            "Cannot auto-merge: main working tree has uncommitted changes. "
                            f"The patch is safely committed on branch '{branch_name}'."
                        ),
                        "diff": diff,
                    }

                active_branch = current_branch(repo_path)
                if active_branch != base_branch:
                    return {
                        "status": "failed",
                        "branch": branch_name,
                        "reason": (
                            f"Cannot auto-merge: active branch in repository is '{active_branch}', "
                            f"not base branch '{base_branch}'. The patch is safely committed on branch '{branch_name}'."
                        ),
                        "diff": diff,
                    }

                merge_res = subprocess.run(
                    ["git", "merge", "--no-ff", "-m", f"merge: {instruction}", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if merge_res.returncode != 0:
                    return {
                        "status": "failed",
                        "branch": branch_name,
                        "reason": f"Merge failed: {merge_res.stderr or merge_res.stdout}",
                        "diff": diff,
                    }
                sandbox.cleanup()

            return {
                "status": "success",
                "branch": branch_name,
                "reason": None,
                "diff": diff,
            }

    except (TargetNotFoundError, AmbiguousTargetError) as e:
        return {"status": "failed", "branch": None, "reason": str(e), "diff": None}


@app.command()
def fix(
    file: str = typer.Option(..., help="Source file containing the target"),
    target: str = typer.Option(..., help="function_name or ClassName.method_name"),
    instruction: str = typer.Option(None, help="Free-text fix instruction"),
    instruction_file: str = typer.Option(None, help="Path to long-form instruction text"),
    test_cmd: str = typer.Option("pytest"),
    lint_cmd: str = typer.Option("ruff check"),
    auto_merge: bool = typer.Option(False),
    base_branch: str = typer.Option(None, help="Defaults to the repo's current branch"),
):
    if instruction is None and instruction_file is None:
        console.print("[red]Provide --instruction or --instruction-file[/red]")
        raise typer.Exit(code=1)
    if instruction is None:
        instruction = Path(instruction_file).read_text()

    llm_client = OpenAICompatibleClient(
        base_url=os.environ.get("ANGRIST_LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.environ.get("ANGRIST_LLM_API_KEY", ""),
        model=os.environ.get("ANGRIST_LLM_MODEL", "gpt-oss"),
    )

    result = run_fix(
        file_path=file,
        target=target,
        instruction=instruction,
        llm_client=llm_client,
        test_cmd=test_cmd,
        lint_cmd=lint_cmd,
        auto_merge=auto_merge,
        base_branch=base_branch,
    )

    if result["status"] == "success":
        console.print(f"[green]Success[/green] on branch {result['branch']}")
        if result["diff"]:
            console.print(result["diff"])
    else:
        console.print(f"[red]Failed[/red]: {result['reason']}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
