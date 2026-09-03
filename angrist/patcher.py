from __future__ import annotations

from typing import Protocol

import httpx


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class OpenAICompatibleClient:
    """Talks to any OpenAI-compatible /chat/completions endpoint.

    Works unmodified against Groq, local Ollama/vLLM OpenAI-compat
    servers, or the real OpenAI API — only base_url/api_key/model
    change.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._http = http_client or httpx.Client()

    def complete(self, prompt: str) -> str:
        response = self._http.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def build_patch_prompt(
    target_source: str, instruction: str, violation_detail: str | None = None
) -> str:
    parts = [
        "You are given the exact source of a single Python function or "
        "class. Return ONLY the complete replacement source for this "
        "node (no explanations, no markdown fences).",
        f"Instruction: {instruction}",
        "Current source:",
        target_source,
    ]
    if violation_detail is not None:
        parts.insert(
            1,
            f"Your previous attempt was rejected: {violation_detail}. "
            "You must only change this node's own body; do not touch "
            "anything else.",
        )
    return "\n\n".join(parts)
