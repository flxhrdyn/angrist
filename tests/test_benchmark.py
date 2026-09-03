import json
from pathlib import Path


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
