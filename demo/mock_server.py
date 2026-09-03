"""Lightweight OpenAI-compatible mock server for zero-dependency demo and testing.

Runs an HTTP server on 127.0.0.1:8000.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

RESPONSES = {
    "calculate_discount": (
        "def calculate_discount(price: float, discount_rate: float) -> float:\n"
        '    """Calculate the final price after discount."""\n'
        "    return price - (price * discount_rate)\n"
    ),
    "withdraw": (
        "    def withdraw(self, amount: float) -> float:\n"
        '        """Withdraw funds from account."""\n'
        "        if amount > self.balance:\n"
        '            raise ValueError("Insufficient funds")\n'
        "        self.balance -= amount\n"
        "        return self.balance\n"
    ),
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
    "_do_load": (
        "    def _do_load(self, data: dict) -> dict:\n"
        "        result = {}\n"
        "        for key, expected_type in self.fields.items():\n"
        "            if key not in data:\n"
        "                continue\n"
        "            val = data[key]\n"
        "            if expected_type is int:\n"
        "                result[key] = int(val)\n"
        "            else:\n"
        "                result[key] = val\n"
        "        return result\n"
    ),
    "add_url_rule": (
        "    def add_url_rule(self, rule: str, endpoint: str) -> None:\n"
        "        prefix = self.url_prefix.rstrip('/')\n"
        "        clean_rule = rule.lstrip('/')\n"
        "        full_rule = f'{prefix}/{clean_rule}' if prefix else f'/{clean_rule}'\n"
        "        self.rules.append((full_rule, endpoint))\n"
    ),
}



class MockOpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        data = json.loads(body)
        messages = data.get("messages", [])
        prompt = messages[-1]["content"] if messages else ""

        fix_content = "def dummy(): pass\n"
        if "calculate_discount" in prompt:
            fix_content = RESPONSES["calculate_discount"]
        elif "withdraw" in prompt:
            fix_content = RESPONSES["withdraw"]
        elif "prepare_url" in prompt:
            fix_content = RESPONSES["prepare_url"]
        elif "_do_load" in prompt:
            fix_content = RESPONSES["_do_load"]
        elif "add_url_rule" in prompt:
            fix_content = RESPONSES["add_url_rule"]


        response_payload = {
            "id": "chatcmpl-mock-angrist",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gpt-oss-mock",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": fix_content,
                    },
                    "finish_reason": "stop",
                }
            ],
        }

        response_bytes = json.dumps(response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format, *args):
        # Suppress noisy standard request logs during demo
        pass


def run_server(port: int = 8000):
    server = HTTPServer(("127.0.0.1", port), MockOpenAIHandler)
    print(f"Mock OpenAI server listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
