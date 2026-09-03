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
    "ASCIIUsernameValidator": (
        "class ASCIIUsernameValidator(RegexValidator):\n"
        "    regex = r'^[\\w.@+-]+\\Z'\n"
        "    message = (\n"
        "        'Enter a valid username. This value may contain only English letters, '\n"
        "        'numbers, and @/./+/-/_ characters.'\n"
        "    )\n"
    ),
    "from_file": (
        "    def from_file(\n"
        "        self,\n"
        "        filename: str,\n"
        "        load: t.Callable[[t.IO[t.Any]], t.Mapping[str, t.Any]],\n"
        "        silent: bool = False,\n"
        "        text: bool = True,\n"
        "    ) -> bool:\n"
        "        filepath = os.path.join(self.root_path, filename)\n"
        "        try:\n"
        "            with open(filepath, 'r' if text else 'rb') as f:\n"
        "                obj = load(f)\n"
        "        except OSError:\n"
        "            if silent:\n"
        "                return False\n"
        "            raise\n"
        "        self.update(obj)\n"
        "        return True\n"
    ),
    "EncodingChecker.open": (
        "    def open(self) -> None:\n"
        "        notes = '|'.join(re.escape(note) for note in self.notes)\n"
        "        regex_string = rf'#\\s*({notes})(?=(:|\\s|\\Z))'\n"
        "        self._fixme_pattern = re.compile(regex_string, re.IGNORECASE)\n"
    ),
    "import_path": (
        "def import_path(path_str: str, root_str: str = '.') -> types.ModuleType:\n"
        "    module_name = path_str.replace('/', '.').replace('\\\\', '.').rstrip('.py')\n"
        "    if module_name in sys.modules:\n"
        "        return sys.modules[module_name]\n"
        "    mod = types.ModuleType(module_name)\n"
        "    mod.__file__ = path_str\n"
        "    sys.modules[module_name] = mod\n"
        "    return mod\n"
    ),
    "DurationField": (
        "class DurationField:\n"
        "    description = 'Duration'\n"
        "    default_error_messages = {\n"
        "        'invalid': \"'%(value)s' value has an invalid format. It must be in [DD] [[HH:]MM:]ss[.uuuuuu] format.\"\n"
        "    }\n\n"
        "    def get_error_message(self, value: str) -> str:\n"
        "        return self.default_error_messages['invalid'] % {'value': value}\n"
    ),
    "inherited_members_option": (
        "def inherited_members_option(arg: Any) -> Union[str, Set[str]]:\n"
        "    if arg in (None, True):\n"
        "        return {'object'}\n"
        "    elif isinstance(arg, str):\n"
        "        return {x.strip() for x in arg.split(',') if x.strip()}\n"
        "    return arg\n"
    ),
    "resolve_redirect_method": (
        "    def resolve_redirect_method(self, status_code: int, original_method: str) -> str:\n"
        "        if status_code in (301, 302, 303):\n"
        "            return 'GET'\n"
        "        return original_method\n"
    ),
    "settle_batch": (
        "    def settle_batch(\n"
        "        self,\n"
        "        transactions: list[Transaction],\n"
        "        exchange_rates: dict[str, Decimal],\n"
        "        base_currency: str = \"USD\",\n"
        "    ) -> SettlementSummary:\n"
        '        """Settle a batch of multi-currency transactions into base currency."""\n'
        '        total_gross = Decimal("0.00")\n'
        '        total_fees = Decimal("0.00")\n'
        "        settled_count = 0\n"
        "        declined_count = 0\n\n"
        "        for tx in transactions:\n"
        "            if tx.status == TransactionStatus.DECLINED:\n"
        "                declined_count += 1\n"
        "                continue\n\n"
        '            rate = exchange_rates.get(tx.currency, Decimal("1.00"))\n'
        "            fee = self.calculate_transaction_fee(tx.amount, is_cross_border=tx.is_cross_border)\n"
        '            converted_amount = (tx.amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)\n'
        '            converted_fee = (fee * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)\n\n'
        "            total_gross += converted_amount\n"
        "            total_fees += converted_fee\n"
        "            tx.fee = fee\n"
        "            tx.status = TransactionStatus.SETTLED\n"
        "            settled_count += 1\n\n"
        "        total_net = total_gross - total_fees\n"
        "        return SettlementSummary(\n"
        "            total_gross=total_gross,\n"
        "            total_net=total_net,\n"
        "            total_fees=total_fees,\n"
        "            settled_count=settled_count,\n"
        "            declined_count=declined_count,\n"
        "        )\n"
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
        if "settle_batch" in prompt or "PaymentProcessor" in prompt:
            fix_content = RESPONSES["settle_batch"]
        elif "calculate_discount" in prompt:
            fix_content = RESPONSES["calculate_discount"]
        elif "withdraw" in prompt:
            fix_content = RESPONSES["withdraw"]
        elif "prepare_url" in prompt:
            fix_content = RESPONSES["prepare_url"]
        elif "_do_load" in prompt:
            fix_content = RESPONSES["_do_load"]
        elif "add_url_rule" in prompt:
            fix_content = RESPONSES["add_url_rule"]
        elif "ASCIIUsernameValidator" in prompt:
            fix_content = RESPONSES["ASCIIUsernameValidator"]
        elif "from_file" in prompt:
            fix_content = RESPONSES["from_file"]
        elif "fixme_pattern" in prompt or "notes" in prompt:
            fix_content = RESPONSES["EncodingChecker.open"]
        elif "import_path" in prompt:
            fix_content = RESPONSES["import_path"]
        elif "DurationField" in prompt:
            fix_content = RESPONSES["DurationField"]
        elif "inherited_members_option" in prompt:
            fix_content = RESPONSES["inherited_members_option"]
        elif "resolve_redirect_method" in prompt or "307" in prompt:
            fix_content = RESPONSES["resolve_redirect_method"]



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
