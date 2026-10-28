"""Typed rule-bundle registration with per-language ownership checks."""

from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import RuleBundle
from code_harness.diagnostics import AnalysisError, Finding


class BundleRegistry:
    """Own bundle identity and rule ownership for one concrete context type."""

    def __init__(self) -> None:
        self._bundles: dict[str, RuleBundle] = {}
        self._rule_owners: dict[str, str] = {}

    @property
    def requires_semantics(self) -> bool:
        return any(bundle.requirements.semantic_evidence for bundle in self._bundles.values())

    def needs_semantics(self, disabled: frozenset[str]) -> bool:
        """Request evidence only for enabled consumers while retaining required capabilities."""
        return any(
            bundle.requirements.semantic_evidence
            and any(rule not in disabled for rule in bundle.rule_ids)
            for bundle in self._bundles.values()
        )

    @property
    def rule_ids(self) -> tuple[str, ...]:
        """Return declared rule IDs in registration order."""
        return tuple(self._rule_owners)

    def register(self, bundle: RuleBundle) -> None:
        """Reject duplicate bundles, incompatible APIs, and conflicting rule owners."""
        if not bundle.name or bundle.name in self._bundles:
            raise AnalysisError(f"Duplicate or empty rule bundle identity: {bundle.name!r}")
        if bundle.api_version != 2:
            raise AnalysisError(f"Unsupported rule bundle API version: {bundle.api_version}")
        self._validate_rules(bundle)
        self._bundles[bundle.name] = bundle
        self._rule_owners.update((rule_id, bundle.name) for rule_id in bundle.rule_ids)

    def _validate_rules(self, bundle: RuleBundle) -> None:
        if not bundle.rule_ids or len(set(bundle.rule_ids)) != len(bundle.rule_ids):
            raise AnalysisError(f"Invalid rule declarations for bundle: {bundle.name}")
        if any(not rule for rule in bundle.rule_ids):
            raise AnalysisError(f"Invalid rule declarations for bundle: {bundle.name}")
        conflicts = set(bundle.rule_ids).intersection(self._rule_owners)
        if conflicts:
            raise AnalysisError(f"Conflicting rule ownership: {', '.join(sorted(conflicts))}")

    def run(
        self, context: TreeContext, disabled: frozenset[str] = frozenset()
    ) -> tuple[Finding, ...]:
        """Skip fully disabled bundles and retain enabled diagnostics from shared bundles."""
        return tuple(
            finding
            for bundle in self._bundles.values()
            if any(rule not in disabled for rule in bundle.rule_ids)
            for finding in self._run_bundle(bundle, context)
            if finding.rule not in disabled
        )

    def _run_bundle(self, bundle: RuleBundle, context: TreeContext) -> tuple[Finding, ...]:
        try:
            findings = bundle.check(context)
            if any(finding.rule not in bundle.rule_ids for finding in findings):
                raise AnalysisError("Bundle emitted an undeclared rule")
            return findings
        except Exception as error:
            raise AnalysisError(f"Rule bundle {bundle.name} failed: {error}") from error
