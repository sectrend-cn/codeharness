"""Narrow tree-backed execution protocols independent of language identities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.plugins.profiles import AnalysisProfile
from code_harness.policy.models import Policy
from code_harness.source import LanguageDefinition, Source

if TYPE_CHECKING:
    from code_harness.analysis.session import AnalysisSession, SemanticBinding


class Analyzer(Protocol):
    """Analyze one registered grammar using application-owned requirements."""

    @property
    def name(self) -> str: ...

    @property
    def definition(self) -> LanguageDefinition: ...

    @property
    def profile(self) -> AnalysisProfile: ...

    @property
    def api_version(self) -> int: ...

    @property
    def rule_ids(self) -> tuple[str, ...]: ...

    @property
    def semantic_binding(self) -> SemanticBinding | None: ...

    def needs_semantics(self, policy: Policy) -> bool: ...

    def validate(self) -> None: ...

    def analyze(
        self, source: Source, policy: Policy, session: AnalysisSession | None = None
    ) -> tuple[Finding, ...]: ...


class RuleBundle(Protocol):
    """Own diagnostic identities and consume the same concrete syntax context."""

    @property
    def name(self) -> str: ...

    @property
    def api_version(self) -> int: ...

    @property
    def rule_ids(self) -> tuple[str, ...]: ...

    @property
    def requirements(self) -> RuleRequirements: ...

    def check(self, context: TreeContext) -> tuple[Finding, ...]: ...


class ContextParser(Protocol):
    """Own tree-sitter parsing, recovery and warning emission."""

    def parse(self, source: Source, policy: Policy) -> TreeContext: ...
