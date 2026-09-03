from __future__ import annotations

import os
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


def _run(cmd: str, cwd) -> subprocess.CompletedProcess:
    """Run a configured lint/test command using POSIX shell argument splitting."""
    args = shlex.split(cmd, posix=True)
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=False
    )


def _check_lint_regression(
    baseline: subprocess.CompletedProcess, candidate: subprocess.CompletedProcess
) -> str | None:
    """True delta gate for linting.

    Passes if no new findings appear, even if baseline had existing lint warnings.
    """
    if candidate.returncode == 0:
        return None
    if baseline.returncode == 0 and candidate.returncode != 0:
        return (
            "lint regressed (clean before the patch):\n"
            f"{candidate.stdout}\n{candidate.stderr}"
        )

    base_lines = [
        line.strip()
        for line in baseline.stdout.splitlines()
        if line.strip() and not line.startswith("Found")
    ]
    cand_lines = [
        line.strip()
        for line in candidate.stdout.splitlines()
        if line.strip() and not line.startswith("Found")
    ]
    if len(cand_lines) > len(base_lines):
        diff = len(cand_lines) - len(base_lines)
        return (
            f"lint regressed: {diff} new finding(s) introduced after patch:\n"
            f"{candidate.stdout}\n{candidate.stderr}"
        )
    return None


def _parse_failed_tests(output: str) -> set[str]:
    failed = set()
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("FAILED "):
            parts = line.split()
            if len(parts) > 1:
                failed.add(parts[1])
    return failed


def _check_test_regression(
    baseline: subprocess.CompletedProcess, candidate: subprocess.CompletedProcess
) -> str | None:
    """True delta gate for tests.

    Passes if no previously-passing tests fail, even if baseline had existing failures.
    """
    if candidate.returncode == 0:
        return None

    base_failed = _parse_failed_tests(baseline.stdout)
    cand_failed = _parse_failed_tests(candidate.stdout)

    if base_failed or cand_failed:
        new_failures = cand_failed - base_failed
        if new_failures:
            return (
                f"tests regressed: {len(new_failures)} test(s) that passed at baseline now fail: "
                f"{', '.join(sorted(new_failures))}"
            )
        if cand_failed and cand_failed == base_failed:
            return (
                "tests still failing after the patch (they were already failing at baseline, "
                f"so this fix did not land): {', '.join(sorted(cand_failed))}"
            )
        return None

    if baseline.returncode == 0 and candidate.returncode != 0:
        return (
            "tests regressed (passing before the patch):\n"
            f"{candidate.stdout}\n{candidate.stderr}"
        )
    if baseline.returncode != 0 and candidate.returncode != 0:
        return (
            "tests still failing after the patch:\n"
            f"{candidate.stdout}\n{candidate.stderr}"
        )
    return None


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

            baseline_lint = _run(lint_cmd, wt_path)
            baseline_test = _run(test_cmd, wt_path)

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

            # H3 FIX: True delta gate for linting
            lint_error = _check_lint_regression(baseline_lint, _run(lint_cmd, wt_path))
            if lint_error:
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": None,
                    "reason": lint_error,
                    "diff": None,
                }

            # H3 FIX: True delta gate for tests
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
                # Check for dirty working tree
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
