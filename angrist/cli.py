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
    """Run a configured lint/test command.

    Normalizes backslashes to forward slashes so POSIX quote stripping works
    without corrupting Windows path delimiters.
    """
    normalized = cmd.replace("\\", "/")
    args = shlex.split(normalized)
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=False
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

    # H4 FIX: Gracefully handle paths outside the repository
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

    # Step 1: Pre-flight target validation before creating sandbox
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

            # H1 FIX: Clean up sandbox on failure before returning
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

            lint_result = _run(lint_cmd, wt_path)
            if (
                lint_result.returncode != 0
                and baseline_lint.returncode == 0
            ):
                branch = sandbox.branch_name
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": branch,
                    "reason": (
                        "lint regressed (clean before the patch): "
                        f"{lint_result.stdout}\n{lint_result.stderr}"
                    ),
                    "diff": None,
                }

            test_result = _run(test_cmd, wt_path)
            if (
                test_result.returncode != 0
                and baseline_test.returncode == 0
            ):
                branch = sandbox.branch_name
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": branch,
                    "reason": (
                        "tests regressed (passing before the patch): "
                        f"{test_result.stdout}\n{test_result.stderr}"
                    ),
                    "diff": None,
                }
            if test_result.returncode != 0 and baseline_test.returncode != 0:
                branch = sandbox.branch_name
                sandbox.cleanup()
                return {
                    "status": "failed",
                    "branch": branch,
                    "reason": (
                        "tests still failing after the patch (they were "
                        "already failing at baseline, so this fix did not "
                        f"land): {test_result.stdout}\n{test_result.stderr}"
                    ),
                    "diff": None,
                }

            diff = subprocess.run(
                ["git", "diff", base_branch], cwd=wt_path, capture_output=True, text=True, check=False
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

            # M4 FIX: Ensure we checkout base_branch before merging
            if auto_merge:
                subprocess.run(
                    ["git", "checkout", base_branch],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "merge", branch_name],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
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
