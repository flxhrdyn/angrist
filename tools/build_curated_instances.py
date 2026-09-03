from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path("benchmarks/swe_bench")
INSTANCES_DIR = BASE_DIR / "instances"


def build_django_11099():
    inst_dir = INSTANCES_DIR / "django__django-11099"
    inst_dir.mkdir(parents=True, exist_ok=True)

    problem = (
        "UsernameValidator allows trailing newline in usernames\n\n"
        "ASCIIUsernameValidator uses the regex r'^[\\w.@+-]+$'. In Python's re engine, "
        "$ matches at the end of the string OR just before a trailing newline (\\n). "
        "Therefore, values like 'validuser\\n' pass validation. "
        "The regex should end with \\Z instead of $ so that trailing newlines are rejected."
    )
    (inst_dir / "problem_statement.txt").write_text(problem, encoding="utf-8")

    pkg = inst_dir / "django" / "contrib" / "auth"
    pkg.mkdir(parents=True, exist_ok=True)
    (inst_dir / "django" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "django" / "contrib" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "django" / "contrib" / "auth" / "__init__.py").write_text("", encoding="utf-8")

    code = '''import re


class RegexValidator:
    regex = ""
    message = "Enter a valid value."

    def __init__(self, regex=None, message=None):
        if regex is not None:
            self.regex = regex
        if message is not None:
            self.message = message
        self._compiled = re.compile(self.regex)

    def __call__(self, value: str) -> None:
        if not self._compiled.search(str(value)):
            raise ValueError(self.message)


class ASCIIUsernameValidator(RegexValidator):
    message = (
        "Enter a valid username. This value may contain only English letters, "
        "numbers, and @/./+/-/_ characters."
    )

    def __init__(self) -> None:
        super().__init__(
            regex=r"^[\\w.@+-]+$",
            message=self.message,
        )
'''
    (pkg / "validators.py").write_text(code, encoding="utf-8")

    test_code = '''import pytest
from django.contrib.auth.validators import ASCIIUsernameValidator


def test_valid_username():
    v = ASCIIUsernameValidator()
    v("valid_user123")
    v("user.name+tag@example")


def test_trailing_newline_rejected():
    v = ASCIIUsernameValidator()
    with pytest.raises(ValueError):
        v("username\\n")
'''
    tests_dir = inst_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_validators.py").write_text(test_code, encoding="utf-8")


def build_flask_4992():
    inst_dir = INSTANCES_DIR / "pallets__flask-4992"
    inst_dir.mkdir(parents=True, exist_ok=True)

    problem = (
        "Add a text/mode parameter to flask.Config.from_file()\n\n"
        "Config.from_file currently always opens files in text mode with open(filename). "
        "When loading TOML or binary config formats using libraries like tomllib.load, "
        "the file must be opened in binary mode ('rb'). "
        "Add a `text: bool = True` parameter to from_file so binary files can be loaded."
    )
    (inst_dir / "problem_statement.txt").write_text(problem, encoding="utf-8")

    pkg = inst_dir / "flask"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    code = '''from __future__ import annotations

import os
import typing as t


class Config(dict):
    def __init__(self, root_path: str = "."):
        super().__init__()
        self.root_path = root_path

    def from_file(
        self,
        filename: str,
        load: t.Callable[[t.IO[t.Any]], t.Mapping[str, t.Any]],
        silent: bool = False,
    ) -> bool:
        """Update the values in the config from a file that is loaded using the load parameter."""
        filepath = os.path.join(self.root_path, filename)
        try:
            with open(filepath) as f:
                obj = load(f)
        except OSError:
            if silent:
                return False
            raise
        self.update(obj)
        return True
'''
    (pkg / "config.py").write_text(code, encoding="utf-8")

    test_code = '''import json
from flask.config import Config


def test_from_file_json(tmp_path):
    p = tmp_path / "test.json"
    p.write_text(json.dumps({"KEY": "VALUE"}))
    c = Config(str(tmp_path))
    assert c.from_file("test.json", load=json.load)
    assert c["KEY"] == "VALUE"


def test_from_file_binary_mode(tmp_path):
    p = tmp_path / "test.bin"
    p.write_bytes(b"KEY=BINARY")

    def binary_loader(f):
        data = f.read()
        assert isinstance(data, bytes)
        k, v = data.decode().split("=")
        return {k: v}

    c = Config(str(tmp_path))
    assert c.from_file("test.bin", load=binary_loader, text=False)
    assert c["KEY"] == "BINARY"
'''
    tests_dir = inst_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_config.py").write_text(test_code, encoding="utf-8")


def build_pylint_5859():
    inst_dir = INSTANCES_DIR / "pylint-dev__pylint-5859"
    inst_dir.mkdir(parents=True, exist_ok=True)

    problem = (
        "--notes option ignores note tags that are entirely punctuation\n\n"
        "In EncodingChecker.open, the fixme regex uses r'#\\s*({notes})\\b'. "
        "Because \\b requires a word boundary (alphanumeric character), note tags "
        "that end in punctuation (like 'FIXME:' or '???') fail to match. "
        "Update the regex to use r'#\\s*({notes})(?=(:|\\s|\\Z))' instead of \\b."
    )
    (inst_dir / "problem_statement.txt").write_text(problem, encoding="utf-8")

    pkg = inst_dir / "pylint" / "checkers"
    pkg.mkdir(parents=True, exist_ok=True)
    (inst_dir / "pylint" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "pylint" / "checkers" / "__init__.py").write_text("", encoding="utf-8")

    code = '''import re


class EncodingChecker:
    def __init__(self, notes: list[str]):
        self.notes = notes
        self._fixme_pattern: re.Pattern | None = None

    def open(self) -> None:
        """Compile fixme pattern from notes configuration."""
        notes = "|".join(re.escape(note) for note in self.notes)
        regex_string = rf"#\\s*({notes})\\b"
        self._fixme_pattern = re.compile(regex_string, re.IGNORECASE)

    def match_note(self, text: str) -> bool:
        if self._fixme_pattern is None:
            self.open()
        return bool(self._fixme_pattern.search(text))
'''
    (pkg / "misc.py").write_text(code, encoding="utf-8")

    test_code = '''from pylint.checkers.misc import EncodingChecker


def test_standard_note_tag():
    checker = EncodingChecker(notes=["FIXME", "TODO"])
    checker.open()
    assert checker.match_note("# FIXME do something")


def test_punctuation_codetag_matches():
    checker = EncodingChecker(notes=["FIXME:", "???"])
    checker.open()
    assert checker.match_note("# FIXME: clean this up")
    assert checker.match_note("# ??? what is this")
'''
    tests_dir = inst_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_misc.py").write_text(test_code, encoding="utf-8")


def build_pytest_11148():
    inst_dir = INSTANCES_DIR / "pytest-dev__pytest-11148"
    inst_dir.mkdir(parents=True, exist_ok=True)

    problem = (
        "Module imported twice under import-mode=importlib in _pytest.pathlib.import_path\n\n"
        "When importing modules using importlib mode, import_path re-imports the module "
        "even if it was already imported in sys.modules, causing type identity checks and singletons "
        "to break. It should check if module_name is already in sys.modules and return it directly."
    )
    (inst_dir / "problem_statement.txt").write_text(problem, encoding="utf-8")

    pkg = inst_dir / "_pytest"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    code = '''import sys
import types


def import_path(path_str: str, root_str: str = ".") -> types.ModuleType:
    """Import a path as a module, respecting sys.modules cache."""
    module_name = path_str.replace("/", ".").replace("\\\\", ".").rstrip(".py")
    # Missing sys.modules check causes re-import bug
    mod = types.ModuleType(module_name)
    mod.__file__ = path_str
    sys.modules[module_name] = mod
    return mod
'''
    (pkg / "pathlib.py").write_text(code, encoding="utf-8")

    test_code = '''from _pytest.pathlib import import_path


def test_import_path_remembers_previous_import():
    mod1 = import_path("my_test_module.py")
    mod1.custom_attr = 42

    mod2 = import_path("my_test_module.py")
    assert mod2 is mod1
    assert getattr(mod2, "custom_attr", None) == 42
'''
    tests_dir = inst_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_pathlib.py").write_text(test_code, encoding="utf-8")


def build_django_11049():
    inst_dir = INSTANCES_DIR / "django__django-11049"
    inst_dir.mkdir(parents=True, exist_ok=True)

    problem = (
        "Correct expected format in invalid DurationField error message\n\n"
        "DurationField default error message states: '[DD] [HH:[MM:]]ss[.uuuuuu] format.' "
        "This is incorrect; HH can only be provided if MM is also provided. "
        "The message should be: '[DD] [[HH:]MM:]ss[.uuuuuu] format.'"
    )
    (inst_dir / "problem_statement.txt").write_text(problem, encoding="utf-8")

    pkg = inst_dir / "django" / "db" / "models" / "fields"
    pkg.mkdir(parents=True, exist_ok=True)
    (inst_dir / "django" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "django" / "db" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "django" / "db" / "models" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "django" / "db" / "models" / "fields" / "__init__.py").write_text("", encoding="utf-8")

    code = '''from typing import ClassVar


class DurationField:
    description = "Duration"
    default_error_messages: ClassVar[dict[str, str]] = {
        "invalid": "'%(value)s' value has an invalid format. It must be in [DD] [HH:[MM:]]ss[.uuuuuu] format."
    }

    def get_error_message(self, value: str) -> str:
        return self.default_error_messages["invalid"] % {"value": value}
'''
    (pkg / "duration.py").write_text(code, encoding="utf-8")

    test_code = '''from django.db.models.fields.duration import DurationField


def test_duration_format_error_message():
    field = DurationField()
    msg = field.get_error_message("invalid-val")
    assert "[DD] [[HH:]MM:]ss[.uuuuuu] format." in msg
    assert "[DD] [HH:[MM:]]ss[.uuuuuu] format." not in msg
'''
    tests_dir = inst_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_durationfield.py").write_text(test_code, encoding="utf-8")


def build_sphinx_10325():
    inst_dir = INSTANCES_DIR / "sphinx-doc__sphinx-10325"
    inst_dir.mkdir(parents=True, exist_ok=True)

    problem = (
        "inherited-members should support more than one class\n\n"
        "In sphinx.ext.autodoc, inherited_members_option converts :members: option. "
        "When arg in (None, True), it returns 'object' as a string. "
        "When comma-separated classes are passed, it should parse them into a set of class names, "
        "and when arg in (None, True), return {'object'}."
    )
    (inst_dir / "problem_statement.txt").write_text(problem, encoding="utf-8")

    pkg = inst_dir / "sphinx" / "ext" / "autodoc"
    pkg.mkdir(parents=True, exist_ok=True)
    (inst_dir / "sphinx" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "sphinx" / "ext" / "__init__.py").write_text("", encoding="utf-8")
    (inst_dir / "sphinx" / "ext" / "autodoc" / "__init__.py").write_text("", encoding="utf-8")

    code = '''from typing import Any


def inherited_members_option(arg: Any) -> str | set[str]:
    """Used to convert the :members: option to auto directives."""
    if arg in (None, True):
        return "object"
    else:
        return arg
'''
    (pkg / "options.py").write_text(code, encoding="utf-8")


    test_code = '''from sphinx.ext.autodoc.options import inherited_members_option


def test_inherited_members_default():
    assert inherited_members_option(True) == {"object"}
    assert inherited_members_option(None) == {"object"}


def test_inherited_members_multiple_classes():
    res = inherited_members_option("Base1, Base2, Base3")
    assert res == {"Base1", "Base2", "Base3"}
'''
    tests_dir = inst_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_autodoc.py").write_text(test_code, encoding="utf-8")


def build_requests_1963():
    inst_dir = INSTANCES_DIR / "psf__requests-1963"
    inst_dir.mkdir(parents=True, exist_ok=True)

    problem = (
        "Method change on 307/308 redirect in SessionRedirect.resolve_redirects\n\n"
        "In requests.sessions.resolve_redirects, responses with HTTP 307 and 308 "
        "must retain their original HTTP method (e.g. POST remains POST). "
        "Only 301, 302, and 303 should convert the request method to GET."
    )
    (inst_dir / "problem_statement.txt").write_text(problem, encoding="utf-8")

    pkg = inst_dir / "requests"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    code = '''class SessionRedirect:
    def resolve_redirect_method(self, status_code: int, original_method: str) -> str:
        """Resolve redirect HTTP method based on status code."""
        # Bug: converts all redirects to GET regardless of 307/308
        if status_code in (301, 302, 303, 307, 308):
            return "GET"
        return original_method
'''
    (pkg / "sessions.py").write_text(code, encoding="utf-8")

    test_code = '''from requests.sessions import SessionRedirect


def test_redirect_303_converts_to_get():
    s = SessionRedirect()
    assert s.resolve_redirect_method(303, "POST") == "GET"


def test_redirect_307_308_preserves_post():
    s = SessionRedirect()
    assert s.resolve_redirect_method(307, "POST") == "POST"
    assert s.resolve_redirect_method(308, "PUT") == "PUT"
'''
    tests_dir = inst_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_sessions.py").write_text(test_code, encoding="utf-8")


def update_manifest():
    manifest_file = BASE_DIR / "manifest.json"
    manifest = {
        "dataset": "SWE-bench_Lite (Curated Representation)",
        "version": "1.0.0",
        "description": "Curated self-contained single-function instances from SWE-bench Lite across diverse domains.",
        "instances": [
            {
                "instance_id": "psf__requests-1142",
                "repo": "psf/requests",
                "directory": "instances/psf__requests-1142",
                "file": "requests/models.py",
                "target": "PreparedRequest.prepare_url",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_models.py"
            },
            {
                "instance_id": "marshmallow__marshmallow-1343",
                "repo": "marshmallow-code/marshmallow",
                "directory": "instances/marshmallow__marshmallow-1343",
                "file": "marshmallow/schema.py",
                "target": "Schema._do_load",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_schema.py"
            },
            {
                "instance_id": "pallets__flask-4045",
                "repo": "pallets/flask",
                "directory": "instances/pallets__flask-4045",
                "file": "flask/blueprints.py",
                "target": "Blueprint.add_url_rule",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_blueprints.py"
            },
            {
                "instance_id": "django__django-11099",
                "repo": "django/django",
                "directory": "instances/django__django-11099",
                "file": "django/contrib/auth/validators.py",
                "target": "ASCIIUsernameValidator.__init__",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_validators.py"
            },
            {
                "instance_id": "pallets__flask-4992",
                "repo": "pallets/flask",
                "directory": "instances/pallets__flask-4992",
                "file": "flask/config.py",
                "target": "Config.from_file",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_config.py"
            },
            {
                "instance_id": "pylint-dev__pylint-5859",
                "repo": "pylint-dev/pylint",
                "directory": "instances/pylint-dev__pylint-5859",
                "file": "pylint/checkers/misc.py",
                "target": "EncodingChecker.open",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_misc.py"
            },
            {
                "instance_id": "pytest-dev__pytest-11148",
                "repo": "pytest-dev/pytest",
                "directory": "instances/pytest-dev__pytest-11148",
                "file": "_pytest/pathlib.py",
                "target": "import_path",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_pathlib.py"
            },
            {
                "instance_id": "django__django-11049",
                "repo": "django/django",
                "directory": "instances/django__django-11049",
                "file": "django/db/models/fields/duration.py",
                "target": "DurationField.get_error_message",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_durationfield.py"
            },
            {
                "instance_id": "sphinx-doc__sphinx-10325",
                "repo": "sphinx-doc/sphinx",
                "directory": "instances/sphinx-doc__sphinx-10325",
                "file": "sphinx/ext/autodoc/options.py",
                "target": "inherited_members_option",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_autodoc.py"
            },
            {
                "instance_id": "psf__requests-1963",
                "repo": "psf/requests",
                "directory": "instances/psf__requests-1963",
                "file": "requests/sessions.py",
                "target": "SessionRedirect.resolve_redirect_method",
                "instruction_file": "problem_statement.txt",
                "test_cmd": "pytest tests/test_sessions.py"
            }
        ]
    }
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Manifest updated with 10 instances!")


def main():
    print("Building 7 new curated SWE-bench instances...")
    build_django_11099()
    build_flask_4992()
    build_pylint_5859()
    build_pytest_11148()
    build_django_11049()
    build_sphinx_10325()
    build_requests_1963()
    update_manifest()
    print("All 10 curated SWE-bench Lite instances successfully built!")


if __name__ == "__main__":
    main()
