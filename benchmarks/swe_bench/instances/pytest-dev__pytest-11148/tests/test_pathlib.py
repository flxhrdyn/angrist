import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from _pytest.pathlib import import_path


def test_import_path_remembers_previous_import():
    mod1 = import_path("my_test_module.py")
    mod1.custom_attr = 42

    mod2 = import_path("my_test_module.py")
    assert mod2 is mod1
    assert getattr(mod2, "custom_attr", None) == 42
