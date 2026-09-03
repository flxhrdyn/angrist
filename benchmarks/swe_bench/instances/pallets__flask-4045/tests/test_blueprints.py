import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask.blueprints import Blueprint


def test_blueprint_prefix_no_double_slash():
    bp = Blueprint("auth", url_prefix="/api/")
    bp.add_url_rule("/login", "login")
    assert bp.rules[0][0] == "/api/login"
