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


_IMPORT_TYPES = {"import_statement", "import_from_statement"}


def _node_name(node) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return name_node.text.decode()
    if node.type == "expression_statement" and len(node.children) > 0:
        first_child = node.children[0]
        if first_child.type == "assignment":
            left = first_child.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                return left.text.decode()
    return None


def _protected_map(source: bytes, root, class_name: str | None, func_name: str):
    """Map every node that must stay byte-identical to its source bytes.

    Key is a path-like identity, e.g. ("function_definition", "bar") for a
    top-level function or ("Foo", "function_definition", "b") for a method
    inside class Foo. Imports and the target node itself are excluded --
    those are the only things allowed to change.
    """
    protected: dict[tuple, bytes] = {}

    for node in root.children:
        if node.type in _IMPORT_TYPES:
            continue

        name = _node_name(node)

        # top-level function target -> excluded from protection
        if class_name is None and node.type == "function_definition" and name == func_name:
            continue

        if node.type == "class_definition" and name == class_name:
            # Descend: protect everything in this class EXCEPT the target
            # method. This is the whole point -- the class is not a
            # blanket whitelist.
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    child_name = _node_name(child)
                    if child.type == "function_definition" and child_name == func_name:
                        continue  # the target method, allowed to change
                    key = (
                        class_name,
                        child.type,
                        child_name,
                        child.start_byte if child_name is None else None,
                    )
                    protected[key] = source[child.start_byte:child.end_byte]
            # also protect the class's own header (name, bases, decorators)
            header_end = body.start_byte if body is not None else node.end_byte
            protected[(class_name, "__class_header__", None, None)] = (
                source[node.start_byte:header_end]
            )
            continue

        key = (None, node.type, name, node.start_byte if name is None else None)
        protected[key] = source[node.start_byte:node.end_byte]

    return protected


def _top_level_names(root) -> set[str]:
    names = set()
    for node in root.children:
        name = _node_name(node)
        if name is not None:
            names.add(name)
    return names


def validate_scope_source(
    original_source: str, candidate_source: str, qualifier: str
) -> None:
    class_name, func_name = parse_target(qualifier)
    orig_bytes = original_source.encode()
    cand_bytes = candidate_source.encode()

    parser = _make_parser()
    orig_root = parser.parse(orig_bytes).root_node
    cand_root = parser.parse(cand_bytes).root_node

    orig_protected = _protected_map(orig_bytes, orig_root, class_name, func_name)
    cand_protected = _protected_map(cand_bytes, cand_root, class_name, func_name)

    orig_names = _top_level_names(orig_root)

    # Every protected original node must survive byte-identical.
    for key, orig_node_bytes in orig_protected.items():
        if key not in cand_protected:
            raise ASTScopeViolationError(
                f"Node {key[:3]} present in the original is missing or "
                f"restructured in your output. Only '{qualifier}' may change."
            )
        if cand_protected[key] != orig_node_bytes:
            raise ASTScopeViolationError(
                f"Node {key[:3]} was modified, but the only node you may "
                f"change is '{qualifier}'."
            )

    # Anything extra in the candidate must be a net-new, non-colliding
    # TOP-LEVEL node. New members inside the target's class are not allowed.
    for key in cand_protected:
        if key in orig_protected:
            continue
        owner, node_type, name = key[0], key[1], key[2]
        if class_name is not None and owner == class_name:
            raise ASTScopeViolationError(
                f"You added '{name}' inside class {class_name}. New members "
                f"may only be added at top level, not inside the target class."
            )
        if name is None:
            raise ASTScopeViolationError(
                f"Unexpected new unnamed {node_type} node at top level."
            )
        if name in orig_names:
            raise ASTScopeViolationError(
                f"New top-level '{name}' collides with an existing name."
            )


def validate_scope(
    original_path: str | Path, candidate_path: str | Path, qualifier: str
) -> None:
    validate_scope_source(
        Path(original_path).read_text(),
        Path(candidate_path).read_text(),
        qualifier,
    )

