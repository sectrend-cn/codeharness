"""Python qualified names, import aliases and expression-use syntax."""

from tree_sitter import Node

from code_harness.parsing.treesitter import field, walk


def _text(node: Node) -> str:
    content = node.text
    if content is None:
        raise ValueError("Python syntax evidence requires retained source text")
    return content.decode("utf-8")


def _expression(node: Node) -> Node:
    while node.type in {"type", "parenthesized_expression"} and node.named_child_count == 1:
        node = node.named_children[0]
    return node


def _name(node: Node, aliases: dict[str, str]) -> str:
    node = _expression(node)
    if node.type in {"identifier", "dotted_name"}:
        name = _text(node)
        return aliases.get(name, name)
    receiver, member = field(node, "object"), field(node, "attribute")
    if node.type == "attribute" and receiver is not None and member is not None:
        return f"{_name(receiver, aliases)}.{_text(member)}"
    return ""


def _aliases(root: Node) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in walk(root):
        if node.type not in {"import_statement", "import_from_statement"}:
            continue
        module = field(node, "module_name")
        for entry in node.children_by_field_name("name"):
            target, alias = field(entry, "name") or entry, field(entry, "alias")
            name = _text(target)
            aliases[_text(alias) if alias is not None else name] = (
                f"{_text(module)}.{name}" if module is not None else name
            )
    return aliases


def _expression_name(node: Node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type in {
        "dotted_name",
        "aliased_import",
        "import_statement",
        "import_from_statement",
        "parameters",
        "list_splat_pattern",
        "dictionary_splat_pattern",
    }:
        return False
    if (
        parent.type
        in {
            "function_definition",
            "class_definition",
            "default_parameter",
            "typed_default_parameter",
            "keyword_argument",
        }
        and field(parent, "name") == node
    ):
        return False
    if parent.type == "typed_parameter" and field(parent, "type") != node:
        return False
    return field(parent, "attribute") != node
