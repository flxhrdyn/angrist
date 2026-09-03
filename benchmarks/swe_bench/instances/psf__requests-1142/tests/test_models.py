import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from requests.models import PreparedRequest


def test_prepare_url_params():
    req = PreparedRequest()
    req.prepare_url("https://example.com/api", {"a": "1", "b": "2"})
    assert req.url == "https://example.com/api?a=1&b=2"
