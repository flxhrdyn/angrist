import httpx

from angrist.patcher import OpenAICompatibleClient, build_patch_prompt


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
