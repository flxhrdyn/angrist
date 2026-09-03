
import httpx
import pytest

from angrist.patcher import (
    OpenAICompatibleClient,
    SanitizationError,
    apply_patch,
    build_patch_prompt,
    sanitize_output,
    target_indent,
)


def _stub_client(expected_body_check=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if expected_body_check is not None:
            expected_body_check(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "def foo():\n    return 42\n"}}]},
        )

    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_complete_returns_message_content():
    http_client = _stub_client()
    client = OpenAICompatibleClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        model="gpt-oss",
        http_client=http_client,
    )
    result = client.complete("fix this function")
    assert result == "def foo():\n    return 42\n"


def test_complete_sends_model_and_auth_header():
    seen = {}

    def check(request: httpx.Request):
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)

    http_client = _stub_client(expected_body_check=check)
    client = OpenAICompatibleClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        model="gpt-oss",
        http_client=http_client,
    )
    client.complete("fix this function")
    assert seen["auth"] == "Bearer test-key"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"


def test_build_patch_prompt_includes_instruction_and_source():
    prompt = build_patch_prompt("def foo():\n    pass\n", "make it return 1")
    assert "def foo():" in prompt
    assert "make it return 1" in prompt


def test_build_patch_prompt_includes_violation_detail_when_present():
    prompt = build_patch_prompt(
        "def foo():\n    pass\n", "make it return 1", violation_detail="you touched bar()"
    )
    assert "you touched bar()" in prompt


def test_sanitize_strips_plain_fences():
    raw = "```\ndef foo(x):\n    return x\n```"
    assert sanitize_output(raw, 0) == "def foo(x):\n    return x\n"


def test_sanitize_strips_fences_with_language_tag():
    raw = "```python\ndef foo(x):\n    return x\n```"
    assert sanitize_output(raw, 0) == "def foo(x):\n    return x\n"


def test_sanitize_reindents_method_to_target_column():
    raw = "def method_a(self, x):\n    return x * 5\n"
    result = sanitize_output(raw, 4)
    assert result == "    def method_a(self, x):\n        return x * 5\n"


def test_sanitize_dedents_overindented_output():
    raw = "        def foo(x):\n            return x\n"
    assert sanitize_output(raw, 0) == "def foo(x):\n    return x\n"


def test_sanitize_rejects_unparseable_output():
    with pytest.raises(SanitizationError):
        sanitize_output("this is not python at all !!!", 0)


def test_sanitize_rejects_prose_wrapped_output():
    raw = "Sure! Here is the fix:\n\ndef foo(x):\n    return x\n"
    with pytest.raises(SanitizationError):
        sanitize_output(raw, 0)


def test_sanitize_rejects_multiple_definitions():
    raw = "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x\n"
    with pytest.raises(SanitizationError):
        sanitize_output(raw, 0)


def test_target_indent_top_level_is_zero(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def foo(x):\n    return x\n")
    assert target_indent(f, "foo") == 0


def test_target_indent_method_is_four(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("class Foo:\n    def a(self):\n        return 1\n")
    assert target_indent(f, "Foo.a") == 4


def test_apply_patch_replaces_target_node_only(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "def foo(x):\n    return x\n\n\ndef bar(x):\n    return x - 1\n"
    )
    apply_patch(target, "foo", "def foo(x):\n    return x + 999\n")

    content = target.read_text()
    assert "return x + 999" in content
    assert "def bar(x):\n    return x - 1" in content


def test_apply_patch_on_class_method(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "class Foo:\n    def method_a(self, x):\n        return x * 2\n"
    )
    apply_patch(
        target, "Foo.method_a", "    def method_a(self, x):\n        return x * 5\n"
    )

    content = target.read_text()
    assert "return x * 5" in content


def test_sanitize_allows_decorated_definition():
    raw = "@property\ndef total(self):\n    return 42\n"
    res = sanitize_output(raw, 0)
    assert "@property" in res
    assert "def total(self):" in res


def test_apply_patch_on_decorated_method(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "class Foo:\n    @property\n    def total(self):\n        return 1\n"
    )
    apply_patch(
        target, "Foo.total", "    @property\n    def total(self):\n        return 100\n"
    )
    content = target.read_text()
    assert "return 100" in content




def test_apply_patch_preserves_blank_line_spacing(tmp_path):
    """The replacement's own trailing newline must not add a blank line."""
    source = tmp_path / "m.py"
    source.write_text("def add(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n")

    apply_patch(source, "add", "def add(a, b):\n    return a + b\n")

    assert source.read_text() == (
        "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
    )


def test_apply_patch_is_idempotent_across_repeated_patches(tmp_path):
    source = tmp_path / "m.py"
    source.write_text("def add(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n")

    for _ in range(3):
        apply_patch(source, "add", "def add(a, b):\n    return a + b\n")

    assert source.read_text().count("\n\n\n") == 1
