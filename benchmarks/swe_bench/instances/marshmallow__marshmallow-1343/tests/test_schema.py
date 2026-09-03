import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from marshmallow.schema import Schema


def test_schema_load_casts_int():
    schema = Schema({"age": int, "name": str})
    loaded = schema._do_load({"age": "25", "name": "Alice"})
    assert loaded["age"] == 25
    assert loaded["name"] == "Alice"
