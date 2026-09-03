from __future__ import annotations

from collections import defaultdict
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
        parts = qualifier.split(".")
        return ".".join(parts[:-1]), parts[-1]
    return None, qualifier


def _inner_definition(node):
    """If node is a decorated_definition, return the underlying definition node."""
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return child
    return node


def _node_name(node) -> str | None:
    inner = _inner_definition(node)
    name_node = inner.child_by_field_name("name")
    if name_node is not None:
        return name_node.text.decode()
    if node.type == "expression_statement" and len(node.children) > 0:
        first_child = node.children[0]
        if first_child.type == "assignment":
            left = first_child.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                return left.text.decode()
    return None


def _find_class_body_blocks(root, class_path: str) -> list:
    """Find all body block nodes for a class path, supporting nested classes."""
    parts = class_path.split(".")
    current_blocks = [root]
    for part in parts:
        next_blocks = []
        for parent in current_blocks:
            for node in parent.children:
                inner = _inner_definition(node)
                if inner.type == "class_definition":
                    name_node = inner.child_by_field_name("name")
                    if name_node is not None and name_node.text.decode() == part:
                        body = inner.child_by_field_name("body")
                        if body is not None:
                            next_blocks.append(body)
        if not next_blocks:
            return []
        current_blocks = next_blocks
    return current_blocks


def _iter_function_defs(tree_root, class_name: str | None):
    """Yield (node, enclosing_class_name_or_None) for every function_definition
    or decorated_definition in the tree, scoped to a class body if class_name is given."""
    if class_name is None:
        for node in tree_root.children:
            inner = _inner_definition(node)
            if inner.type == "function_definition":
                yield node, None
        return

    # Nested class support
    blocks = _find_class_body_blocks(tree_root, class_name)
    for body in blocks:
        for child in body.children:
            inner = _inner_definition(child)
            if inner.type == "function_definition":
                yield child, class_name


def _find_target_nodes(tree_root, qualifier: str) -> list:
    class_name, func_name = parse_target(qualifier)
    matches = []
    for node, _ in _iter_function_defs(tree_root, class_name):
        inner = _inner_definition(node)
        name_node = inner.child_by_field_name("name")
        if name_node is not None and name_node.text.decode() == func_name:
            matches.append(node)
    return matches


def extract_node_source_from_bytes(source: bytes, qualifier: str) -> str:
    parser = _make_parser()
    tree = parser.parse(source)
    matches = _find_target_nodes(tree.root_node, qualifier)
    if not matches:
        raise TargetNotFoundError(f"No target matching '{qualifier}' found")
    if len(matches) > 1:
        raise AmbiguousTargetError(
            f"Qualifier '{qualifier}' matches {len(matches)} nodes; refine the qualifier"
        )
    node = matches[0]
    return source[node.start_byte:node.end_byte].decode()


def extract_node_source(file_path: str | Path, qualifier: str) -> str:
    source = Path(file_path).read_bytes()
    try:
        return extract_node_source_from_bytes(source, qualifier)
    except TargetNotFoundError:
        raise TargetNotFoundError(
            f"No target matching '{qualifier}' found in {file_path}"
        )
    except AmbiguousTargetError:
        raise AmbiguousTargetError(
            f"Qualifier '{qualifier}' matches multiple nodes in {file_path}; refine the qualifier"
        )


_IMPORT_TYPES = {"import_statement", "import_from_statement"}


def _protected_map(source: bytes, root, class_name: str | None, func_name: str):
    """Map every node that must stay byte-identical to its source bytes.

    Uses structural occurrence counts rather than start_byte so that shifts
    in byte offset when the target changes size do NOT trigger false violations (C2, M2).
    """
    protected: dict[tuple, bytes] = {}
    counts: dict[tuple, int] = defaultdict(int)

    def process_children(parent_node, owner_prefix: str | None):
        for node in parent_node.children:
            if node.type in _IMPORT_TYPES:
                continue

            inner = _inner_definition(node)
            name = _node_name(node)

            # Check if this is the target function
            if (
                owner_prefix == class_name
                and inner.type == "function_definition"
                and name == func_name
            ):
                continue  # Target node itself is allowed to change

            # Check if this is a class definition on the target class path
            if inner.type == "class_definition" and class_name is not None:
                current_full_class = (
                    f"{owner_prefix}.{name}" if owner_prefix else name
                )
                if class_name == current_full_class or class_name.startswith(f"{current_full_class}."):
                    # Descend into this class: protect members individually
                    body = inner.child_by_field_name("body")
                    if body is not None:
                        process_children(body, current_full_class)
                    # Protect class header (decorators, class name, base classes)
                    header_end = body.start_byte if body is not None else node.end_byte
                    occurrence = counts[(current_full_class, "__class_header__", None)]
                    counts[(current_full_class, "__class_header__", None)] += 1
                    protected[(current_full_class, "__class_header__", None, occurrence)] = (
                        source[node.start_byte:header_end]
                    )
                    continue

            # General node: key is (owner_prefix, node.type, name, occurrence)
            occurrence = counts[(owner_prefix, node.type, name)]
            counts[(owner_prefix, node.type, name)] += 1
            key = (owner_prefix, node.type, name, occurrence)
            protected[key] = source[node.start_byte:node.end_byte]

    process_children(root, None)
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

    # C3 FIX: Ensure target node still exists in candidate!
    cand_matches = _find_target_nodes(cand_root, qualifier)
    if not cand_matches:
        raise ASTScopeViolationError(
            f"Target '{qualifier}' was deleted or renamed in your output. "
            f"You must keep the target function name and definition intact."
        )

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
