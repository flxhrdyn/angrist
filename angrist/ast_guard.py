from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())


class TargetNotFoundError(Exception):
    pass


class AmbiguousTargetError(Exception):
    pass


class ASTScopeViolationError(Exception):
    pass


def _make_parser() -> Parser:
    return Parser(PY_LANGUAGE)


def parse_target(qualifier: str) -> tuple[str | None, str]:
    if "." in qualifier:
        class_name, func_name = qualifier.split(".", 1)
        return class_name, func_name
    return None, qualifier


def _iter_function_defs(tree_root, class_name: str | None):
    """Yield (node, enclosing_class_name_or_None) for every function_definition
    node in the tree, scoped to a class body if class_name is given."""
    if class_name is None:
        for node in tree_root.children:
            if node.type == "function_definition":
                yield node, None
        return

    for node in tree_root.children:
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.text.decode() == class_name:
                body = node.child_by_field_name("body")
                if body is not None:
                    for child in body.children:
                        if child.type == "function_definition":
                            yield child, class_name


def extract_node_source(file_path: str | Path, qualifier: str) -> str:
    class_name, func_name = parse_target(qualifier)
    source = Path(file_path).read_bytes()
    parser = _make_parser()
    tree = parser.parse(source)

    matches = []
    for node, _ in _iter_function_defs(tree.root_node, class_name):
        name_node = node.child_by_field_name("name")
        if name_node is not None and name_node.text.decode() == func_name:
            matches.append(node)

    if not matches:
        raise TargetNotFoundError(
            f"No target matching '{qualifier}' found in {file_path}"
        )
    if len(matches) > 1:
        raise AmbiguousTargetError(
            f"Qualifier '{qualifier}' matches {len(matches)} nodes in "
            f"{file_path}; refine the qualifier"
        )

    node = matches[0]
    return source[node.start_byte:node.end_byte].decode()
