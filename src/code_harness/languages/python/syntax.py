"""Python-specific metrics and dependency interpretation."""

import posixpath

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.architecture.models import Import
from code_harness.languages.comments import GrammarComments
from code_harness.languages.metric_syntax import GrammarMetrics
from code_harness.languages.python.type_syntax import _aliases, _expression_name, _name
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.source import Source


def _docstring_scope(node: Node) -> bool:
    if node.type == "module":
        return True
    return (
        node.type == "block"
        and node.parent is not None
        and node.parent.type in {"function_definition", "class_definition"}
    )


def _docstring(node: Node) -> bool:
    if node.type != "expression_statement":
        return False
    parent = node.parent
    if parent is None or not _docstring_scope(parent):
        return False
    statements = [child for child in parent.named_children if child.type != "comment"]
    return bool(
        statements
        and statements[0] == node
        and node.named_children
        and node.named_children[0].type in {"string", "concatenated_string"}
    )


class PythonMetrics(GrammarMetrics):
    """Exclude docstrings and implicit Python receivers."""

    def is_docstring(self, node: Node) -> bool:
        return _docstring(node)

    def parameter_count(self, node: Node, source: Source) -> int:
        return int(spelling(node, source) not in {"self", "cls"})


class PythonImports:
    """Resolve Python module and member imports from the original recovered tree."""

    def extract(self, context: TreeContext) -> tuple[Import, ...]:
        imports: list[Import] = []
        for node in walk(context.root):
            names = self._modules(node, context.source)
            imports.extend(
                Import(name, node.start_point.row + 1, node.start_point.column + 1)
                for name in names
            )
        return tuple(imports)

    def _modules(self, node: Node, source: Source) -> tuple[str, ...]:
        if node.type == "import_statement":
            return tuple(self._name(child, source) for child in node.children_by_field_name("name"))
        if node.type != "import_from_statement":
            return ()
        module_node = field(node, "module_name")
        if module_node is None:
            return ()
        module = self._module_name(module_node, source)
        names = [self._name(child, source) for child in node.children_by_field_name("name")]
        if any(child.type == "wildcard_import" for child in node.named_children):
            names.append("*")
        return (module, *(f"{module}.{name}".strip(".") for name in names))

    def _module_name(self, module_node: Node, source: Source) -> str:
        raw = spelling(module_node, source)
        level = len(raw) - len(raw.lstrip("."))
        package = posixpath.dirname(source.path).split("/")
        parts = package[: len(package) - level + 1] if level else []
        if raw.lstrip("."):
            parts.append(raw.lstrip("."))
        return ".".join(parts)

    def _name(self, node: Node, source: Source) -> str:
        target = field(node, "name") if node.type == "aliased_import" else node
        return spelling(target or node, source)


class PythonSuppressions(GrammarComments):
    """Identify aliases of typing markers that disable checking."""

    requirements = RuleRequirements(semantic_evidence=True)

    def disabled_types(self, context: TreeContext) -> tuple[Node, ...]:
        aliases = _aliases(context.root)
        return tuple(
            node
            for node in walk(context.root)
            if node.type in {"identifier", "attribute"}
            and _expression_name(node)
            and _name(node, aliases) in {"typing.no_type_check", "typing.no_type_check_decorator"}
        )
