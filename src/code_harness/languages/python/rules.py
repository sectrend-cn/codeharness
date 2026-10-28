"""Python contract checks over the shared tree-sitter source context."""

from dataclasses import dataclass

import tree_sitter_python
from tree_sitter import Language as Grammar
from tree_sitter import Node, Parser

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.languages.python.type_syntax import (
    _aliases,
    _expression,
    _expression_name,
    _name,
    _text,
)
from code_harness.parsing.treesitter import field, walk
from code_harness.policy.type_options import ANNOTATION, ASSERTION, SIGNATURE, WILDCARD
from code_harness.semantics.encoding import EncodingRule
from code_harness.semantics.encoding_options import BROAD_TYPE
from code_harness.source import Source

_BROAD = frozenset({"Any", "object", "JsonValue", "BaseModel"})
_BARE = frozenset(
    {
        "list",
        "dict",
        "set",
        "tuple",
        "frozenset",
        "List",
        "Dict",
        "Set",
        "Tuple",
        "Mapping",
        "MutableMapping",
        "Sequence",
        "Iterable",
        "Iterator",
        "Callable",
    }
)


def _finding(source: Source, node: Node, rule: str, message: str) -> Finding:
    return Finding(
        path=source.path,
        line=node.start_point.row + 1,
        column=node.start_point.column + 1,
        rule=rule,
        message=message,
    )


def _annotations(root: Node) -> tuple[Node, ...]:
    result: list[Node] = []
    for node in walk(root):
        annotation = None
        if node.type in {"typed_parameter", "typed_default_parameter", "assignment"}:
            annotation = field(node, "type")
        elif node.type == "function_definition":
            annotation = field(node, "return_type")
        elif node.type == "type_alias_statement":
            annotation = field(node, "right")
        if annotation is not None and not annotation.has_error:
            result.append(_expression(annotation))
    return tuple(result)


def _string_value(node: Node) -> str | None:
    if node.type == "concatenated_string":
        parts: list[str] = []
        for child in node.named_children:
            value = _string_value(child)
            if value is None:
                return None
            parts.append(value)
        return "".join(parts)
    start = next((child for child in node.named_children if child.type == "string_start"), None)
    if start is None:
        return None
    return _decode_string(node, _text(start).lower())


def _decode_string(node: Node, prefix: str) -> str | None:
    """Decode Python text literals while preserving UTF-8 characters and raw strings."""
    if "b" in prefix or "f" in prefix:
        return None
    content = "".join(
        _text(child) for child in node.named_children if child.type == "string_content"
    )
    if "r" in prefix:
        return content
    try:
        return content.encode("ascii", "backslashreplace").decode("unicode_escape")
    except UnicodeDecodeError:
        return None


def _forward_issues(annotation: str, aliases: dict[str, str]) -> tuple[str, ...]:
    tree = Parser(Grammar(tree_sitter_python.language())).parse(annotation.encode("utf-8"))
    root = tree.root_node
    statements = tuple(child for child in root.named_children if child.type != "comment")
    if root.has_error or len(statements) != 1:
        return ("Invalid forward type annotation",)
    statement = statements[0]
    if statement.type != "expression_statement" or statement.named_child_count != 1:
        return ("Invalid forward type annotation",)
    expression = statement.named_children[0]
    if expression.type in {"assignment", "augmented_assignment", "yield"}:
        return ("Invalid forward type annotation",)
    return _annotation_issues(expression, aliases)


def _generic_parts(expression: Node) -> tuple[Node | None, list[Node]]:
    if expression.type == "generic_type":
        base, parameters = expression.named_children
        return base, parameters.named_children
    return field(expression, "value"), expression.children_by_field_name("subscript")


def _has_ellipsis(arguments: list[Node]) -> bool:
    return any(node.type == "ellipsis" for argument in arguments for node in walk(argument))


def _generic_issues(expression: Node, aliases: dict[str, str]) -> tuple[str, ...]:
    base, arguments = _generic_parts(expression)
    name = _name(base, aliases).rsplit(".", 1)[-1] if base is not None else ""
    if name == "Literal":
        return ()
    if name == "Annotated" and arguments:
        return _annotation_issues(arguments[0], aliases)
    issues = [issue for argument in arguments for issue in _annotation_issues(argument, aliases)]
    if name in _BROAD:
        issues.append(f"Preserve a concrete contract instead of {name}")
    if name == "Callable" and _has_ellipsis(arguments):
        issues.append("Preserve Callable parameter types instead of ellipsis")
    return tuple(issues)


def _string_issues(expression: Node, aliases: dict[str, str]) -> tuple[str, ...]:
    value = _string_value(expression)
    if value is not None:
        return _forward_issues(value, aliases)
    return tuple(
        issue
        for child in expression.named_children
        if child.type == "interpolation"
        for issue in _annotation_issues(child, aliases)
    )


def _annotation_issues(expression: Node, aliases: dict[str, str]) -> tuple[str, ...]:
    if expression.type in {"string", "concatenated_string"}:
        return _string_issues(expression, aliases)
    if expression.type in {"generic_type", "subscript"}:
        return _generic_issues(expression, aliases)
    name = _name(expression, aliases).rsplit(".", 1)[-1]
    if name in _BROAD:
        return (f"Preserve a concrete contract instead of {name}",)
    if name in _BARE:
        return (f"Supply concrete element types for {name}",)
    return tuple(
        issue for child in expression.named_children for issue in _annotation_issues(child, aliases)
    )


def _splat_names(parameter: Node) -> tuple[str, ...]:
    return tuple(
        _text(child)
        for child in parameter.named_children
        if child.type == "identifier" and _text(child) not in {"self", "cls"}
    )


def _untyped_parameters(parameters: Node) -> list[str]:
    missing: list[str] = []
    variadic: list[str] = []
    for parameter in parameters.named_children:
        if field(parameter, "type") is not None:
            continue
        name = field(parameter, "name") or parameter
        if name.type in {"list_splat_pattern", "dictionary_splat_pattern"}:
            variadic.extend(_splat_names(name))
        elif name.type == "identifier" and _text(name) not in {"self", "cls"}:
            missing.append(_text(name))
    return [*missing, *variadic]


def _signature_findings(source: Source, node: Node) -> tuple[Finding, ...]:
    if node.type != "function_definition" or node.has_error:
        return ()
    parameters = field(node, "parameters")
    if parameters is None:
        return ()
    missing = _untyped_parameters(parameters)
    if field(node, "return_type") is None:
        missing.append("return")
    return (
        (
            _finding(
                source,
                node,
                SIGNATURE.name,
                f"Declare concrete interface types: {', '.join(missing)}",
            ),
        )
        if missing
        else ()
    )


def _escape_findings(source: Source, node: Node, aliases: dict[str, str]) -> tuple[Finding, ...]:
    callee = field(node, "function") if node.type == "call" else None
    if callee is not None:
        name = _name(callee, aliases)
        if name in {"typing.cast", "typing_extensions.cast", "typing.no_type_check"}:
            return (_finding(source, node, ASSERTION.name, f"Do not bypass typing with {name}"),)
    if node.type in {"identifier", "attribute"} and _expression_name(node):
        return _marker_findings(source, node, _name(node, aliases))
    if node.type == "import_from_statement" and any(
        child.type == "wildcard_import" for child in node.named_children
    ):
        return (_finding(source, node, WILDCARD.name, "Import explicit supported names"),)
    return ()


def _marker_findings(source: Source, node: Node, name: str) -> tuple[Finding, ...]:
    if name in {"typing.Any", "typing_extensions.Any", "pydantic.JsonValue"}:
        return (_finding(source, node, BROAD_TYPE.name, f"Do not erase contracts with {name}"),)
    return ()


@dataclass(frozen=True)
class PythonTypeRule:
    """Own Python annotation, interface and escape policy over tree evidence."""

    encoding: EncodingRule
    name: str = "builtin.types.python"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements(semantic_evidence=True)
    rule_ids: tuple[str, ...] = (
        ANNOTATION.name,
        SIGNATURE.name,
        ASSERTION.name,
        BROAD_TYPE.name,
        WILDCARD.name,
    )

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        aliases = _aliases(context.root)
        boundary = context.require_boundary()
        findings: list[Finding] = []
        for expression in _annotations(context.root):
            if boundary.contains(expression):
                continue
            for issue in _annotation_issues(expression, aliases):
                findings.append(_finding(context.source, expression, ANNOTATION.name, issue))
        for node in walk(context.root):
            findings.extend(_signature_findings(context.source, node))
            if not boundary.contains(node):
                findings.extend(_escape_findings(context.source, node, aliases))
        findings.extend(self.encoding.check(context))
        return tuple(findings)
