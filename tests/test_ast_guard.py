from pathlib import Path

import pytest

from angrist.ast_guard import (
    AmbiguousTargetError,
    TargetNotFoundError,
    extract_node_source,
    parse_target,
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
