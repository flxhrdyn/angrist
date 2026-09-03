from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

OUTPUT_PATH = Path("benchmarks/swe_bench/official_manifest.json")


def parse_patch_target(patch: str) -> tuple[str | None, str | None]:
    """Extract modified file and target function/class from a git patch."""
    files = re.findall(r"diff --git a/(.*?) b/", patch)
    target_file = files[0] if files else None

    hunks = re.findall(r"@@ -\d+,\d+ \+\d+,\d+ @@ (.*)", patch)
    func_names = []
    for h in hunks:
        m = re.search(r"def ([a-zA-Z0-9_]+)", h)
        if m:
            func_names.append(m.group(1))
        else:
            m2 = re.search(r"class ([a-zA-Z0-9_]+)", h)
            if m2:
                func_names.append(m2.group(1))

    # Prefer most frequently touched or first unique function
    target_func = func_names[0] if func_names else None
    return target_file, target_func


def fetch_official_swebench_lite() -> list[dict]:
    """Fetch all 300 instances from official princeton-nlp/SWE-bench_Lite on Hugging Face."""
    all_rows = []
    for offset in [0, 100, 200]:
        url = (
            "https://datasets-server.huggingface.co/rows?"
            f"dataset=princeton-nlp/SWE-bench_Lite&config=default&split=test&offset={offset}&limit=100"
        )
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        all_rows.extend([item["row"] for item in data.get("rows", [])])

    instances = []
    for row in all_rows:
        patch = row.get("patch", "")
        target_file, target_func = parse_patch_target(patch)

        instances.append(
            {
                "instance_id": row["instance_id"],
                "repo": row["repo"],
                "base_commit": row["base_commit"],
                "file": target_file,
                "target": target_func,
                "problem_statement": row["problem_statement"],
                "fail_to_pass": row.get("FAIL_TO_PASS", []),
                "pass_to_pass": row.get("PASS_TO_PASS", []),
                "has_single_function_patch": target_func is not None,
            }
        )

    return instances


def main():
    print("Fetching official SWE-bench Lite (300 instances) from Hugging Face...")
    instances = fetch_official_swebench_lite()
    single_func_count = sum(1 for inst in instances if inst["has_single_function_patch"])

    manifest_data = {
        "dataset": "princeton-nlp/SWE-bench_Lite",
        "total_instances": len(instances),
        "single_function_instances": single_func_count,
        "source": "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite",
        "instances": instances,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    print(f"Saved {len(instances)} instances to {OUTPUT_PATH}")
    print(f"Single-function target instances: {single_func_count}/{len(instances)}")


if __name__ == "__main__":
    main()
