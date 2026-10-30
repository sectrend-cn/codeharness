# Language and rule architecture

The architecture uses a common tree-sitter context, independently
registered languages and rules, typed grammar capabilities, and application-owned
required coverage. This document records the current architecture and its
compatibility behavior.

## Ownership and interfaces

| Boundary | Owner and contract |
| --- | --- |
| Language identity | `LanguageDefinition` declares an open identity and suffixes; required rules belong to an application profile |
| Parsing | `ContextParser` produces `TreeContext` backed by a concrete tree-sitter `Tree`; `.root` exposes its root `Node` |
| Grammar interpretation | Language adapters implement the consuming domain's narrow syntax protocols |
| Rule behavior | `RuleBundle` consumes `TreeContext` and declares identity, API version, diagnostic IDs and `RuleRequirements` |
| Checker configuration | Owner-local typed fragments declare schemas and identities; `policy.models.Checkers` explicitly composes them |
| Application policy | `AnalysisProfile` specifies required diagnostic coverage and explicitly unavailable optional analysis |
| Composition | `plugins/builtins.py` connects language adapters, shared rules and language-specific checks |
| Execution | `TypedAnalyzer` validates its composition, uses the session's parse and runs enabled bundles |
| Session lifetime | `AnalysisSession` owns exact snapshot parsing and reusable semantic evidence within one execution |
| Registration | Language discovery and rule ownership are registered separately; `AnalyzerRegistry` validates composed analyzers |

Checker configuration and its compatibility contract are described in
[Checker-owned registration](checker-configuration.md#checker-owned-registration).

Required capabilities are explicit. A rule that consumes semantic evidence
requires it through `RuleRequirements`; metrics and architecture rules receive
their grammar contracts through typed construction. Registration and execution
validate availability without inspecting rule identities or concrete rule classes.
Validation runs before enable flags can skip analysis, and rules added after
analyzer construction cannot bypass capability checks.

All language-specific node interpretation stays with language adapters or specific
language rules. Shared algorithms retain concrete domain contracts and tree nodes;
there are no generic payload dictionaries, casts or secondary Python ASTs.
Python annotations and forward annotation expressions are handled with its
registered tree-sitter grammar. Parser warnings disclose recovery limitations;
infrastructure and required capability failures remain analysis errors.

Package placement follows behavior ownership. Shared rules sit with the policy
that executes them: metrics in `metrics/`, dependency checks in `architecture/`,
and usage and boundary checks in `semantics/`. Language-specific rules live beside
the grammar they interpret, and there is no root-level catch-all rule package.
Language plugins do not assemble analyzers or select shared rule sets, and shared
analysis and rules do not import concrete language plugins. Application
composition imports concrete languages and rules, binds them through typed
construction and dispatches on no language identity; the CLI and snapshot
infrastructure stay outside domain analysis. Snapshot identity includes content
and grammar, so staged and working-tree sources never share stale evidence.
Conflicting contents for one semantic module within one execution are rejected
explicitly, sessions reject a different policy, and a selected source snapshot
takes precedence over a reference with the same language and path.

Java is registered through the same composition. Its grammar interpretation
and type policy live in `languages/java/`; shared engines never import that
package. `BindingSyntax.inherited_types` returns `tuple[Node, ...]` so a language
can expose multiple independent inheritance clauses. Custom semantic adapters
must return an empty tuple when there are no bases. Java's checked scope and
resolution limits follow the shared per-checker coverage in
[checker configuration](checker-configuration.md).

## Shared alias and output analysis

`semantics/aliases.py` owns stable callable/module alias resolution and constructor
provenance. `NameSyntax` supplies transparent grammar expressions, imported-name
identity and recognized built-ins. Resolution uses the canonical semantic index;
cycles, shadowing and multiple assignments do not become guessed destinations.

`semantics/flow.py` owns single-assignment carrier and container forwarding. Its
`Destinations` protocol classifies a use as permitted, rejected or requiring further
traversal. Both third-party boundary evidence and serialization checks use this
same algorithm. An internal use cannot be hidden by another permitted output use.

`EncodingRule` consumes `EncodingSyntax`, which identifies encoders, decoders,
argument consumers and actual output APIs. Its `argument` capability returns the
canonical `ParameterSlot` for a payload; this lets shared semantics enforce
configured positional/keyword output selectors without reading grammar fields.
`BroadTypeOptions.encoding` owns validated additive encoder, decoder and output
API declarations. Explicit decoder evidence wins over configured output matches. A decoder rejection takes precedence
over a configured library-input exemption. Grammar/API interpretation lives in
`languages/`; shared semantic code imports no concrete language or grammar and
contains no language-name dispatch.

Application composition supplies Python, Go, Java and JavaScript adapters. Their
type-rule objects receive an `EncodingRule` through their constructor
and retain ownership of their combined `type.broad` diagnostics; JavaScript
registers that rule directly. This keeps diagnostic ownership unique. Custom
construction of `PythonTypeRule`, `GoTypeRule`, `JavaTypeRule` or
`TypeScriptTypeRule` must supply the encoding rule explicitly. They reuse the
session's existing context and boundary index.

Current serializer adapters cover Python `json.dumps` and JavaScript/TypeScript/TSX
`JSON.stringify`, imported Go JSON Marshal/MarshalIndent and selected imported
Gson/Jackson Java serializers. Exact scoped instance outputs are available in all
registered languages. Java interprets invocation nodes and functional-interface
fields; Go supplies the proven first payload binding of a byte/error result.
Shared flow checks that binding's every read and leaves sibling error results
independent. Exact supported signatures and conservative limits are documented in
[Checker configuration](checker-configuration.md#source-owned-instance-output-callbacks).

## Shared guarded projection analysis

`GuardedProjectionRule` consumes the language-owned `ProjectionSyntax` capability
and existing session semantic index. `semantics/projection/` owns checker options,
binding identity, candidate evidence and consecutive-region clustering.
`languages/projection_syntax.py` shares the grammar operations, and each language
supplies its predicate and construction interpretation through `ProjectionSyntax`.
Language code cannot import the projection rule implementation; shared matching
imports no language implementation and selects no language identity. Built-in
composition requires this diagnostic for Python, Go, Java, JS, TS and TSX, and a
new language must supply equivalent adapters and behavioral tests before claiming
coverage. Exact syntax coverage and conservative limits are documented in
[the guarded projection checker reference](../.agents/skills/code-harness/references/checkers/structure.guarded_projection.md).

## Changed-scope capability

`Source.changed_lines` is `None` for a full audit and a concrete frozen set for
changed snapshots, including deletion anchors. Built-in analyzers receive a
`ScopeSyntax` adapter through `TypedAnalyzer.scopes`. The shared `AffectedScopes`
consumer expands edits using grammar-owned definition extents and class headers,
then filters emitted diagnostics. It never truncates the parsed snapshot or
semantic evidence. Rules declare file-level obligations with `Finding.scope="file"`;
the default is `"line"`. Ownership and placement use file scope, without rule-ID
dispatch in the shared filter.
Custom `TypedAnalyzer` compositions must supply this capability for changed-scope
runs; missing capability fails visibly instead of silently claiming scoped checks.
Full-source library calls remain compatible with the default `Source` constructor.

## Extending the application

A shared rule consumes the same concrete context regardless of source language:

```python
@dataclass(frozen=True)
class ModuleSizeRule:
    name: str = "project.module_size"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements()
    rule_ids: tuple[str, ...] = ("project.module_size",)

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        if context.root.named_child_count <= 100:
            return ()
        return (Finding(path=context.source.path, line=1, column=1,
                        rule="project.module_size", message="Split module responsibilities"),)
```

This example bounds top-level named syntax nodes; their meaning is grammar-defined.
A rule requiring a normalized concept such as executable statements must consume
the appropriate typed syntax capability instead of assuming identical node shapes.

`builtin_analyzers()` returns concrete `TypedAnalyzer` objects. Extend their
`bundles` before registering them in an `AnalyzerRegistry`. Use `builtin_registry()`
for the standard application composition. Pass the same registry to discovery and
execution; `cli.main(arguments, analyzers=registry)` provides that integration.
Rules do not declare a list of language identities. Applicability and grammar
capability bindings belong to application composition.

For a new language, declare its identity, suffixes, grammar and adapters; build an
application profile and compatible rule bundle registry; then compose and register
its analyzer. All extension parsers now return `TreeContext`. The count-dialect
fixture in `tests/test_extensions.py` uses a registered tree-sitter grammar and
verifies discovery, CLI findings, source selection and session lifetime through
the same public extension path.

## Compatibility and failure behavior

Extension contracts are defined over the common tree context rather than a
language-specific one:

- Extensions consume the shared `TreeContext`.
- `ContextParser`, `RuleBundle`, `BundleRegistry` and `TypedAnalyzer` take no
  arbitrary context type parameters.
- Rules declare capabilities through explicit requirements; applicability and
  grammar capability bindings belong to application composition.
- Language plugins do not assemble analyzers; built-in assembly is
  application-owned.
- `AnalysisProfile.required_rules` declares required diagnostic coverage.
- Custom analyzers provide `validate()`, `needs_semantics(policy)` and accept an
  optional execution session; they expose a typed optional `semantic_binding`,
  which registration attaches automatically, and remain responsible for their
  declared contract and failures.

The configuration schema and the extension API are separate compatibility
boundaries. Registration rejects legacy-shaped extension objects, ambiguous
suffixes, invalid identities, missing required coverage and conflicting rule
ownership.
Undeclared findings and executing plugin failures still fail closed. Disabled
bundles do not execute; disabling all rules avoids parsing after composition
validation. Required coverage remains independent of checker enable flags.

Analysis runs on tree-sitter recovery and checks over the available syntax. A
custom parser that raises `SyntaxFailure` supplies `tuple[ParseWarning, ...]` and
must explain in its warnings which dependent checks are unavailable. Recovery
differences must remain tested and documented. Source selection stays
snapshot-based and gate execution stays read-only.
