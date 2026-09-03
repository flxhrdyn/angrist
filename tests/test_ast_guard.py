from pathlib import Path

import pytest

from angrist.ast_guard import (
    ASTScopeViolationError,
    TargetNotFoundError,
    extract_node_source,
    parse_target,
    validate_scope,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_module.py"


def test_parse_target_function_only():
    assert parse_target("top_level_func") == (None, "top_level_func")


def test_parse_target_class_method():
    assert parse_target("Foo.method_a") == ("Foo", "method_a")


def test_extract_top_level_function():
    src = extract_node_source(FIXTURE, "top_level_func")
    assert "def top_level_func(x):" in src
    assert "return x + 1" in src


def test_extract_class_method_disambiguates_duplicate_names():
    src_foo = extract_node_source(FIXTURE, "Foo.method_a")
    assert "return x * 2" in src_foo

    src_bar = extract_node_source(FIXTURE, "Bar.method_a")
    assert "return x * 3" in src_bar


def test_extract_missing_target_raises():
    with pytest.raises(TargetNotFoundError):
        extract_node_source(FIXTURE, "does_not_exist")


def test_extract_missing_class_raises():
    with pytest.raises(TargetNotFoundError):
        extract_node_source(FIXTURE, "NoSuchClass.method_a")


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return p


def test_validate_scope_allows_target_change_only(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "def foo(x):\n    return x + 1\n\n\ndef bar(x):\n    return x - 1\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return x + 100\n\n\ndef bar(x):\n    return x - 1\n",
    )
    validate_scope(original, candidate, "foo")  # should not raise


def test_validate_scope_allows_import_change(tmp_path):
    original = _write(tmp_path, "orig.py", "import os\n\n\ndef foo(x):\n    return x\n")
    candidate = _write(tmp_path, "cand.py", "import os\nimport sys\n\n\ndef foo(x):\n    return x\n")
    validate_scope(original, candidate, "foo")  # should not raise


def test_validate_scope_allows_new_noncolliding_top_level(tmp_path):
    original = _write(tmp_path, "orig.py", "def foo(x):\n    return x\n")
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return helper(x)\n\n\ndef helper(x):\n    return x + 1\n",
    )
    validate_scope(original, candidate, "foo")  # should not raise


def test_validate_scope_rejects_new_top_level_name_collision(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x\n\n\ndef bar(y):\n    return y\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "foo")


def test_validate_scope_rejects_unrelated_node_edit(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x - 1\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x - 999\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "foo")


def test_validate_scope_allows_target_method_change(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "class Foo:\n"
        "    def a(self):\n        return 1\n\n"
        "    def b(self):\n        return 2\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "class Foo:\n"
        "    def a(self):\n        return 100\n\n"
        "    def b(self):\n        return 2\n",
    )
    validate_scope(original, candidate, "Foo.a")  # should not raise


def test_validate_scope_rejects_sibling_method_edit(tmp_path):
    """The critical case: targeting Foo.a must NOT license edits to Foo.b."""
    original = _write(
        tmp_path, "orig.py",
        "class Foo:\n"
        "    def a(self):\n        return 1\n\n"
        "    def b(self):\n        return 2\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "class Foo:\n"
        "    def a(self):\n        return 100\n\n"
        "    def b(self):\n        return 999\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "Foo.a")


def test_validate_scope_rejects_class_attribute_edit(tmp_path):
    original = _write(
        tmp_path, "orig.py",
        "class Foo:\n"
        "    LIMIT = 10\n\n"
        "    def a(self):\n        return 1\n",
    )
    candidate = _write(
        tmp_path, "cand.py",
        "class Foo:\n"
        "    LIMIT = 999\n\n"
        "    def a(self):\n        return 1\n",
    )
    with pytest.raises(ASTScopeViolationError):
        validate_scope(original, candidate, "Foo.a")

