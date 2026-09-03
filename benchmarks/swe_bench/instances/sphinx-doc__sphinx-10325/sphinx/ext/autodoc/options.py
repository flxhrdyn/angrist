from typing import Any


def inherited_members_option(arg: Any) -> str | set[str]:
    """Used to convert the :members: option to auto directives."""
    if arg in (None, True):
        return "object"
    else:
        return arg
