"""Application composition for independently registered grammars and rules."""

from dataclasses import dataclass
from functools import lru_cache

from code_harness.analysis.analyzer import TypedAnalyzer
from code_harness.analysis.contracts import RuleBundle
from code_harness.architecture.design import ObjectDesignRule
from code_harness.architecture.design_contracts import DesignSyntax
from code_harness.architecture.imports import (
    ImportExtractor,
    ImportResolver,
    LiteralImportResolver,
)
from code_harness.architecture.options import DISPATCH, IMPORTS, OBJECT_MODEL, OWNERSHIP, STRUCTURE
from code_harness.architecture.rules import ArchitectureRule
from code_harness.diagnostics import AnalysisError
from code_harness.languages import comments
from code_harness.languages.change_scopes import GrammarScopes
from code_harness.languages.design_syntax import GrammarDesignSyntax
from code_harness.languages.go import GoLanguage
from code_harness.languages.go.encoding import GoEncodingSyntax
from code_harness.languages.go.projection import GoProjection
from code_harness.languages.go.rules import GoTypeRule
from code_harness.languages.go.syntax import GoImports, GoMetrics
from code_harness.languages.java import JavaLanguage
from code_harness.languages.java.encoding import JavaEncodingSyntax
from code_harness.languages.java.projection import JavaProjection
from code_harness.languages.java.rules import JavaSuppressions, JavaTypeRule
from code_harness.languages.java.semantic_syntax import JavaSemanticSyntax
from code_harness.languages.java.syntax import JavaDesignSyntax, JavaImports, JavaMetrics
from code_harness.languages.javascript import JavaScriptLanguage
from code_harness.languages.javascript.encoding import JavaScriptEncodingSyntax
from code_harness.languages.javascript.projection import JavaScriptProjection
from code_harness.languages.javascript.syntax import (
    JavaScriptImports,
    JavaScriptMetrics,
    RelativeImportResolver,
)
from code_harness.languages.python import PythonLanguage
from code_harness.languages.python.encoding import PythonEncodingSyntax
from code_harness.languages.python.projection import PythonProjection
from code_harness.languages.python.rules import PythonTypeRule
from code_harness.languages.python.syntax import PythonImports, PythonMetrics, PythonSuppressions
from code_harness.languages.semantic_syntax import (
    GoSemanticSyntax,
    JavaScriptSemanticSyntax,
    PythonSemanticSyntax,
)
from code_harness.languages.typescript import TsxLanguage, TypeScriptLanguage
from code_harness.languages.typescript.rules import TypeScriptTypeRule
from code_harness.languages.typescript.semantic_syntax import TypeScriptSemanticSyntax
from code_harness.languages.typescript.syntax import TypeScriptImports
from code_harness.metrics.contracts import MetricSyntax
from code_harness.metrics.options import FUNCTION_SIZE
from code_harness.metrics.rules import MetricRule
from code_harness.parsing.treesitter import TreeParser
from code_harness.plugins.bundles import BundleRegistry
from code_harness.plugins.languages import LanguagePlugin
from code_harness.plugins.profiles import AnalysisProfile
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.policy.type_options import ANNOTATION, ASSERTION, SIGNATURE, SUPPRESSION, WILDCARD
from code_harness.semantics.boundaries import BoundaryRule
from code_harness.semantics.encoding import EncodingRule
from code_harness.semantics.encoding_options import BROAD_TYPE
from code_harness.semantics.model import SemanticSyntax
from code_harness.semantics.options import BOUNDARY, USAGE_RULES
from code_harness.semantics.projection.contracts import ProjectionSyntax
from code_harness.semantics.projection.options import GUARDED_PROJECTION
from code_harness.semantics.projection.rules import GuardedProjectionRule
from code_harness.semantics.usage import UsageRule
from code_harness.source import Language
from code_harness.suppressions import DirectiveSyntax, SuppressionRule

_BASE_RULES = (
    *USAGE_RULES,
    *BOUNDARY.rule_ids,
    *SUPPRESSION.rule_ids,
    *FUNCTION_SIZE.rule_ids,
    OWNERSHIP.name,
    STRUCTURE.name,
    IMPORTS.name,
    DISPATCH.name,
    OBJECT_MODEL.name,
    GUARDED_PROJECTION.name,
)


@dataclass(frozen=True)
class _Capabilities:
    """Bind consumer-owned syntax interfaces without a heterogeneous registry."""

    metrics: MetricSyntax
    imports: ImportExtractor
    resolver: ImportResolver
    semantics: SemanticSyntax
    design: DesignSyntax
    projection: ProjectionSyntax


@lru_cache(maxsize=1)
def builtin_languages() -> tuple[LanguagePlugin, ...]:
    """Register only grammar identity and discovery at this seam."""
    return (
        PythonLanguage(),
        GoLanguage(),
        JavaScriptLanguage(),
        TypeScriptLanguage(),
        TsxLanguage(),
        JavaLanguage(),
    )


def _compose(
    plugin: LanguagePlugin,
    syntax: _Capabilities,
    rules: tuple[RuleBundle, ...],
    required: tuple[str, ...],
    directives: DirectiveSyntax | None = None,
) -> TypedAnalyzer:
    bundles = BundleRegistry()
    for rule in rules:
        bundles.register(rule)
    shared_rules: tuple[RuleBundle, ...] = (
        UsageRule(),
        BoundaryRule(),
        MetricRule(syntax.metrics),
        ArchitectureRule(syntax.imports, syntax.resolver),
        ObjectDesignRule(syntax.design),
        GuardedProjectionRule(syntax.projection),
    )
    for shared in shared_rules:
        bundles.register(shared)
    return TypedAnalyzer(
        f"builtin.{plugin.definition.language.value}",
        plugin.definition,
        plugin.parser,
        bundles,
        AnalysisProfile((*_BASE_RULES, *required)),
        syntax.semantics,
        scopes=GrammarScopes(syntax.semantics),
        directives=directives,
    )


def _python_analyzer(plugin: LanguagePlugin) -> TypedAnalyzer:
    syntax = _Capabilities(
        PythonMetrics(),
        PythonImports(),
        LiteralImportResolver(),
        PythonSemanticSyntax(),
        GrammarDesignSyntax(),
        PythonProjection(),
    )
    required = (
        ANNOTATION.name,
        SIGNATURE.name,
        ASSERTION.name,
        BROAD_TYPE.name,
        WILDCARD.name,
    )
    directives = comments.DirectiveSyntax(frozenset({"comment"}), "#")
    rules = (
        PythonTypeRule(EncodingRule(PythonEncodingSyntax())),
        SuppressionRule(PythonSuppressions(), directives=directives),
    )
    return _compose(plugin, syntax, rules, required, directives)


def _go_analyzer(plugin: LanguagePlugin) -> TypedAnalyzer:
    syntax = _Capabilities(
        GoMetrics(),
        GoImports(),
        LiteralImportResolver(),
        GoSemanticSyntax(),
        GrammarDesignSyntax(),
        GoProjection(),
    )
    directives = comments.DirectiveSyntax(frozenset({"comment"}), "//")
    return _compose(
        plugin,
        syntax,
        (
            GoTypeRule(EncodingRule(GoEncodingSyntax())),
            SuppressionRule(comments.GrammarComments(), directives=directives),
        ),
        (BROAD_TYPE.name,),
        directives,
    )


def _java_analyzer(plugin: LanguagePlugin) -> TypedAnalyzer:
    syntax = _Capabilities(
        JavaMetrics(),
        JavaImports(),
        LiteralImportResolver(),
        JavaSemanticSyntax(),
        JavaDesignSyntax(),
        JavaProjection(),
    )
    directives = comments.DirectiveSyntax(frozenset({"line_comment", "block_comment"}), "//")
    rules = (
        JavaTypeRule(EncodingRule(JavaEncodingSyntax())),
        SuppressionRule(JavaSuppressions(), directives=directives),
    )
    return _compose(plugin, syntax, rules, (BROAD_TYPE.name, ASSERTION.name), directives)


def _javascript_analyzer(plugin: LanguagePlugin) -> TypedAnalyzer:
    syntax = _Capabilities(
        JavaScriptMetrics(),
        JavaScriptImports(),
        RelativeImportResolver(),
        JavaScriptSemanticSyntax(),
        GrammarDesignSyntax(),
        JavaScriptProjection(),
    )
    directives = comments.DirectiveSyntax(frozenset({"comment"}), "//")
    rules = (
        EncodingRule(JavaScriptEncodingSyntax()),
        SuppressionRule(comments.GrammarComments(), directives=directives),
    )
    return _compose(plugin, syntax, rules, (BROAD_TYPE.name,), directives)


def _typescript_analyzer(plugin: LanguagePlugin) -> TypedAnalyzer:
    syntax = _Capabilities(
        JavaScriptMetrics(),
        TypeScriptImports(),
        RelativeImportResolver(),
        TypeScriptSemanticSyntax(),
        GrammarDesignSyntax(),
        JavaScriptProjection(),
    )
    directives = comments.DirectiveSyntax(frozenset({"comment"}), "//")
    rules = (
        TypeScriptTypeRule(EncodingRule(JavaScriptEncodingSyntax())),
        SuppressionRule(comments.GrammarComments(), directives=directives),
    )
    return _compose(plugin, syntax, rules, (ASSERTION.name, BROAD_TYPE.name), directives)


def builtin_analyzers() -> tuple[TypedAnalyzer, ...]:
    """Bind grammar capabilities to independent shared and exceptional rule policies."""
    python, go, javascript, typescript, tsx, java = builtin_languages()
    return (
        _python_analyzer(python),
        _go_analyzer(go),
        _javascript_analyzer(javascript),
        _typescript_analyzer(typescript),
        _typescript_analyzer(tsx),
        _java_analyzer(java),
    )


def tree_parser(language: Language) -> TreeParser:
    """Resolve the compatibility parser facade through language registration."""
    parsers = {plugin.definition.language: plugin.parser for plugin in builtin_languages()}
    try:
        return parsers[language]
    except KeyError as error:
        raise AnalysisError(f"No tree parser registered for {language}") from error


def builtin_registry() -> AnalyzerRegistry:
    """Compose isolated analyzer registrations and their typed session capabilities."""
    registry = AnalyzerRegistry()
    for analyzer in builtin_analyzers():
        registry.register(analyzer)
    return registry
