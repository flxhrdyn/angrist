import json
from pathlib import Path

from angrist.benchmark import run_benchmark_suite


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
        assert (instance_dir / item["instruction_file"]).exists()


class StubBenchmarkClient:
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def complete(self, prompt: str) -> str:
        for key, resp in self.mapping.items():
            if key in prompt:
                return resp
        return "def fallback(): pass\n"


def test_run_benchmark_suite(tmp_path):
    from angrist.benchmark import run_benchmark_suite

    responses = {
        "prepare_url": (
            "    def prepare_url(self, url: str, params: dict | None = None) -> None:\n"
            "        if not params:\n"
            "            self.url = url\n"
            "            return\n"
            "        scheme, netloc, path, params_part, query, fragment = urlparse(url)\n"
            "        encoded = urlencode(params)\n"
            "        new_query = f'{query}&{encoded}' if query else encoded\n"
            "        self.url = urlunparse((scheme, netloc, path, params_part, new_query, fragment))\n"
        ),
    }

    client = StubBenchmarkClient(responses)
    output_json = tmp_path / "results.json"
    manifest = Path("benchmarks/swe_bench/manifest.json")

    summary = run_benchmark_suite(
        manifest_path=manifest,
        filter_pattern="requests",
        llm_client=client,
        output_json=output_json,
    )

    assert summary.total == 1
    assert summary.passed == 1
    assert summary.failed == 0
    assert summary.resolved_rate == 1.0
    assert output_json.exists()
    saved_data = json.loads(output_json.read_text())
    assert saved_data["summary"]["total"] == 1
    assert saved_data["summary"]["passed"] == 1


def test_render_benchmark_table_and_panel():
    from rich.panel import Panel
    from rich.table import Table

    from angrist.benchmark import (
        BenchmarkCaseResult,
        BenchmarkSummary,
        render_benchmark_table,
        render_summary_panel,
    )

    results = [
        BenchmarkCaseResult(
            instance_id="inst-1",
            repo="repo/1",
            target="target1",
            status="passed",
            duration_seconds=1.23,
            reason=None,
        ),
        BenchmarkCaseResult(
            instance_id="inst-2",
            repo="repo/2",
            target="target2",
            status="failed",
            duration_seconds=2.34,
            reason="tests failed",
        ),
    ]
    summary = BenchmarkSummary(
        total=2,
        passed=1,
        failed=1,
        resolved_rate=0.5,
        total_duration_seconds=3.57,
        instances=results,
    )

    tbl = render_benchmark_table(results)
    pnl = render_summary_panel(summary)

    assert isinstance(tbl, Table)
    assert isinstance(pnl, Panel)




def test_run_benchmark_suite_leaves_no_worktree_or_branch_after_success():
    """The cleanup after a passing instance must actually remove the sandbox
    worktree and branch run_fix() left behind -- res["branch"] is a branch
    name, not a worktree path, and passing it straight to
    `git worktree remove` silently fails (verified: exits 128, 'not a
    working tree'), leaking a worktree and an undeletable branch per
    successful instance."""
    import subprocess

    responses = {
        "prepare_url": (
            "    def prepare_url(self, url: str, params: dict | None = None) -> None:\n"
            "        if not params:\n"
            "            self.url = url\n"
            "            return\n"
            "        scheme, netloc, path, params_part, query, fragment = urlparse(url)\n"
            "        encoded = urlencode(params)\n"
            "        new_query = f'{query}&{encoded}' if query else encoded\n"
            "        self.url = urlunparse((scheme, netloc, path, params_part, new_query, fragment))\n"
        ),
    }
    client = StubBenchmarkClient(responses)
    manifest = Path("benchmarks/swe_bench/manifest.json")

    before = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True, check=False
    ).stdout

    summary = run_benchmark_suite(
        manifest_path=manifest, filter_pattern="requests", llm_client=client
    )
    assert summary.passed == 1

    after = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True, check=False
    ).stdout
    assert after == before

    branches = subprocess.run(
        ["git", "branch", "--list", "angrist-sandbox-*"], capture_output=True, text=True, check=False
    ).stdout
    assert branches.strip() == ""
