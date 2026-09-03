"""Lightweight OpenAI-compatible mock server for zero-dependency demo and testing.

Runs an HTTP server on 127.0.0.1:8000.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

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
