from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Protocol

import httpx

from angrist.ast_guard import (
    AmbiguousTargetError,
    TargetNotFoundError,
    _find_target_nodes,
    _inner_definition,
    _make_parser,
)


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class OpenAICompatibleClient:
    """Talks to any OpenAI-compatible /chat/completions endpoint.

    Works unmodified against Groq, local Ollama/vLLM OpenAI-compat
    servers, or the real OpenAI API - only base_url/api_key/model
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
        self._http = http_client or httpx.Client(timeout=120.0)

    def complete(self, prompt: str) -> str:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = self._http.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
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
        (
            "You are given the exact source of a single Python function or "
            "class. Return ONLY the complete replacement source for this "
            "node (no explanations, no markdown fences)."
        ),
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


class SanitizationError(Exception):
    pass


def _strip_fences(raw: str) -> str:
    lines = raw.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines)


def sanitize_output(raw: str, target_indent_cols: int) -> str:
    """Turn raw model output into exactly one correctly-indented node.

    Mechanical, not prompt-dependent: open-weight models wrap output in
    fences and guess indentation no matter what the prompt says, so the
    guarantee lives here.
    """
    text = _strip_fences(raw)
    text = textwrap.dedent(text).strip("\n")
    if not text:
        raise SanitizationError("Model returned empty output.")

    parser = _make_parser()
    root = parser.parse(text.encode()).root_node

    if root.has_error:
        raise SanitizationError(
            "Output did not parse as valid Python. Return only the "
            "replacement function or class body, with no prose."
        )

    definitions = []
    for c in root.children:
        inner = _inner_definition(c)
        if inner.type in ("function_definition", "class_definition"):
            definitions.append(c)

    if len(definitions) != 1 or len(root.children) != 1:
        raise SanitizationError(
            f"Expected exactly one function or class definition and nothing "
            f"else, got {len(root.children)} top-level node(s). Return only "
            f"the replacement node."
        )

    if target_indent_cols:
        text = textwrap.indent(text, " " * target_indent_cols)
    return text + "\n"


def _resolve_target_node(source: bytes, qualifier: str):
    tree = _make_parser().parse(source)
    matches = _find_target_nodes(tree.root_node, qualifier)
    if not matches:
        raise TargetNotFoundError(f"No target matching '{qualifier}' found")
    if len(matches) > 1:
        raise AmbiguousTargetError(
            f"Qualifier '{qualifier}' matches {len(matches)} nodes"
        )
    return matches[0]


def target_indent(file_path: str | Path, qualifier: str) -> int:
    source = Path(file_path).read_bytes()
    node = _resolve_target_node(source, qualifier)
    return node.start_point[1]


def apply_patch(file_path: str | Path, qualifier: str, new_node_source: str) -> None:
    path = Path(file_path)
    source = path.read_bytes()
    node = _resolve_target_node(source, qualifier)

    new_bytes = new_node_source.encode()
    if not new_bytes.endswith(b"\n"):
        new_bytes += b"\n"
    # node.start_byte sits at the first character of the definition, past
    # its leading indentation; sanitize_output already re-indented the
    # replacement, so trim its leading whitespace on the first line to
    # avoid doubling it.
    line_start = source.rfind(b"\n", 0, node.start_byte) + 1
    leading = source[line_start:node.start_byte]
    if leading.strip() == b"" and new_bytes.startswith(leading):
        new_bytes = new_bytes[len(leading):]

    updated = source[: node.start_byte] + new_bytes + source[node.end_byte :]
    path.write_bytes(updated)
