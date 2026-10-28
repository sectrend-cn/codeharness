"""Compatibility exports for language-owned semantic syntax adapters."""

from code_harness.languages.go.semantic_syntax import GoSemanticSyntax
from code_harness.languages.javascript.semantic_syntax import JavaScriptSemanticSyntax
from code_harness.languages.python.semantic_syntax import PythonSemanticSyntax

__all__ = ["GoSemanticSyntax", "JavaScriptSemanticSyntax", "PythonSemanticSyntax"]
