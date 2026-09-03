from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from angrist.cli import run_fix
from angrist.config import load_config
from angrist.patcher import LLMClient, OpenAICompatibleClient


@dataclass
class BenchmarkCaseResult:
    instance_id: str
    repo: str
    target: str
    status: str  # "passed", "failed", "error"
    duration_seconds: float
    reason: str | None = None


@dataclass
class BenchmarkSummary:
    total: int
    passed: int
    failed: int
    resolved_rate: float
    total_duration_seconds: float
    instances: list[BenchmarkCaseResult]


def render_benchmark_table(results: list[BenchmarkCaseResult]) -> Table:
    """Render a modern high-contrast terminal results table using Catppuccin palette."""
    table = Table(
        title="[bold #06b6d4]SWE-bench Benchmark Results[/bold #06b6d4]",
        box=ROUNDED,
        header_style="bold #94a3b8",
        border_style="#6366f1",
        show_header=True,
    )
    table.add_column("Instance ID", style="bold #06b6d4", justify="left")
    table.add_column("Target", style="#f8fafc", justify="left")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right", style="dim #94a3b8")
    table.add_column("Details", justify="left", style="#cbd5e1")

    for r in results:
        if r.status == "passed":
            status_badge = "[bold #10b981]PASS[/bold #10b981]"
        elif r.status == "failed":
            status_badge = "[bold #f43f5e]FAIL[/bold #f43f5e]"
        else:
            status_badge = "[bold #f59e0b]ERROR[/bold #f59e0b]"

        details = r.reason or "Fixed and verified"
        if len(details) > 60:
            details = details[:57] + "..."

        table.add_row(
            r.instance_id,
            r.target,
            status_badge,
            f"{r.duration_seconds:.2f}s",
            details,
        )

    return table


def render_summary_panel(summary: BenchmarkSummary) -> Panel:
    """Render a highlighted summary card for the benchmark run."""
    pass_pct = f"{summary.resolved_rate * 100:.1f}%"
    rate_color = "#10b981" if summary.resolved_rate >= 0.8 else ("#f59e0b" if summary.resolved_rate >= 0.5 else "#f43f5e")

    content = (
        f"[bold #f8fafc]Total Instances Tested:[/bold #f8fafc] {summary.total}\n"
        f"[bold #f8fafc]Resolved / Pass Rate:[/bold #f8fafc] [{rate_color}]{summary.passed}/{summary.total} ({pass_pct})[/{rate_color}]\n"
        f"[bold #f8fafc]Failed / Regressed:[/bold #f8fafc] [bold #f43f5e]{summary.failed}[/bold #f43f5e]\n"
        f"[bold #f8fafc]Total Duration:[/bold #f8fafc] [dim #94a3b8]{summary.total_duration_seconds:.2f}s[/dim #94a3b8]"
    )

    return Panel(
        content,
        title="[bold #06b6d4]Benchmark Evaluation Summary[/bold #06b6d4]",
        box=ROUNDED,
        border_style="#6366f1",
        padding=(1, 2),
    )


def run_benchmark_suite(
    manifest_path: str | Path,
    filter_pattern: str | None = None,
    llm_client: LLMClient | None = None,
    repo_path: str | Path = ".",
    max_retries: int = 3,
    output_json: str | Path | None = None,
    console: Console | None = None,
) -> BenchmarkSummary:
    """Execute curated SWE-bench benchmark instances and collect results."""
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text())
    instances = data.get("instances", [])

    if filter_pattern:
        regex = re.compile(filter_pattern, re.IGNORECASE)
        instances = [
            inst for inst in instances
            if regex.search(inst["instance_id"]) or regex.search(inst["repo"])
        ]

    if llm_client is None:
        cfg = load_config()
        llm_client = OpenAICompatibleClient(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
        )

    results: list[BenchmarkCaseResult] = []
    start_suite_time = time.time()

    for item in instances:
        instance_id = item["instance_id"]
        instance_dir_rel = item["directory"]
        manifest_dir = manifest_path.parent
        instance_dir = manifest_dir / instance_dir_rel

        file_rel = str(instance_dir / item["file"]).replace("\\", "/")
        instruction_file = instance_dir / item["instruction_file"]
        instruction = instruction_file.read_text().strip()
        target = item["target"]

        # Adapt test command to run relative to workspace root
        raw_test_cmd = item["test_cmd"]
        if raw_test_cmd.startswith("pytest "):
            test_target = raw_test_cmd[len("pytest "):].strip()
            effective_test_cmd = f"pytest {instance_dir}/{test_target}".replace("\\", "/")
        else:
            effective_test_cmd = raw_test_cmd


        case_start = time.time()
        try:
            res = run_fix(
                file_path=file_rel,
                target=target,
                instruction=instruction,
                llm_client=llm_client,
                repo_path=str(repo_path),
                test_cmd=effective_test_cmd,
                lint_cmd="python -c pass",
                auto_merge=False,
                max_retries=max_retries,
            )
            duration = time.time() - case_start
            status = "passed" if res["status"] == "success" else "failed"
            reason = res.get("reason")

            # Clean up the sandbox worktree and branch created by the unmerged test run
            if res.get("branch"):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", res["branch"]],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    ["git", "branch", "-D", res["branch"]],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                )


            results.append(
                BenchmarkCaseResult(
                    instance_id=instance_id,
                    repo=item["repo"],
                    target=target,
                    status=status,
                    duration_seconds=duration,
                    reason=reason,
                )
            )
        except (subprocess.SubprocessError, OSError, ValueError, RuntimeError) as e:
            duration = time.time() - case_start

            results.append(
                BenchmarkCaseResult(
                    instance_id=instance_id,
                    repo=item["repo"],
                    target=target,
                    status="error",
                    duration_seconds=duration,
                    reason=str(e),
                )
            )

    total_duration = time.time() - start_suite_time
    passed_count = sum(1 for r in results if r.status == "passed")
    total_count = len(results)
    resolved_rate = (passed_count / total_count) if total_count > 0 else 0.0

    summary = BenchmarkSummary(
        total=total_count,
        passed=passed_count,
        failed=total_count - passed_count,
        resolved_rate=resolved_rate,
        total_duration_seconds=total_duration,
        instances=results,
    )

    if output_json is not None:
        out_path = Path(output_json)
        json_data = {
            "summary": {
                "total": summary.total,
                "passed": summary.passed,
                "failed": summary.failed,
                "resolved_rate": summary.resolved_rate,
                "total_duration_seconds": summary.total_duration_seconds,
            },
            "instances": [asdict(r) for r in summary.instances],
        }
        out_path.write_text(json.dumps(json_data, indent=2))

    if console is not None:
        console.print(render_benchmark_table(results))
        console.print(render_summary_panel(summary))

    return summary
