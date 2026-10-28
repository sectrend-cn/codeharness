# Language and rule architecture

The approved API 2 design uses a common tree-sitter context, independently
registered languages and rules, typed grammar capabilities, and application-owned
required coverage. See the [source structure and migration design](language-rule-decoupling.md).
Implementation validation is recorded with that design; the API 1 material at the
end of this document is historical.

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
[Checker-owned registration](checker-configuration.md#checker-owned-registration--2026-10-08).

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

Java is registered through the same API 2 composition. Its grammar interpretation
and type policy live in `languages/java/`; shared engines never import that
package. `BindingSyntax.inherited_types` returns `tuple[Node, ...]` so a language
can expose multiple independent inheritance clauses. Custom semantic adapters
must return an empty tuple when there are no bases. See [Java support](java-support.md)
for checked scope and resolution limits.

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
independent. [Language extension](instance-output-language-extension.md) records
supported signatures, conservative limits and current validation evidence.

## Shared guarded projection analysis

`GuardedProjectionRule` consumes the language-owned `ProjectionSyntax` capability
and existing session semantic index. `semantics/projection/` owns checker options,
binding identity, candidate evidence and consecutive-region clustering. Built-in
composition requires this diagnostic for Python, Go, Java, JS, TS and TSX; syntax
coverage and limits are documented in [Guarded field projections](guarded-projection.md).

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

API 2 intentionally changes the extension contracts:

- `PythonContext` and `ast.Module` consumers migrate to the common tree context.
- `ContextParser`, `RuleBundle`, `BundleRegistry` and `TypedAnalyzer` no longer take
  arbitrary context type parameters.
- Rules replace language lists with explicit requirements and composition bindings.
- Language plugins stop assembling analyzers; built-in assembly is application-owned.
- `LanguageDefinition.required_rules` moves to `AnalysisProfile`.
- Custom analyzers provide `validate()`, `needs_semantics(policy)` and accept an
  optional execution session;
  they expose a typed optional `semantic_binding`, which registration attaches
  automatically, and remain responsible for their declared contract and failures.

The configuration schema remains version 2; extension API version 2 is a separate
compatibility boundary. Registration rejects API 1 objects, ambiguous suffixes,
invalid identities, missing required coverage and conflicting rule ownership.
Undeclared findings and executing plugin failures still fail closed. Disabled
bundles do not execute; disabling all rules avoids parsing after composition
validation. Required coverage remains independent of checker enable flags.

The runtime no longer emits CPython AST-rejection warnings. Tree-sitter recovery
and checks over available syntax replace that behavior; valid annotations with
type comments no longer lose all Python type/import checks because a second parser
rejected the source. Recovery differences must remain tested and documented.
Source selection stays snapshot-based and gate execution stays read-only.

## Historical API 1 reference

The remaining sections describe the former implementation and its dated
validation evidence. They preserve design history and are not API 2 extension
instructions or evidence that the current change has passed its checks.

Languages and rules are explicit in-process object plugins. A new language owns
its identity, suffixes, parser, typed context, required rules, and composition.
Adding one does not require changing source discovery or engine dispatch. A new
rule implements `RuleBundle[ItsContext]` and registers with that context's bundle
registry. Built-in checker options and independent enable flags live under
`Policy.checkers`; automatic package discovery is not implemented.

Language-specific rule modules live with their language plugins. The Python
plugin composes `languages/python_rules.py`, which owns Python annotation,
explicit type escape and JSON encoding checks. Shared rule engines and semantic
infrastructure remain with their own shared responsibilities. Directory placement
must express the actual owner, and moves must update both imports and repository
ownership/dependency policy without broadening exemptions.

### Ownership and interfaces

| Boundary | Owner and contract |
| --- | --- |
| Source identity | `source.Language` is an immutable open identity; `LanguageDefinition` declares suffixes and required rules |
| Parser lifecycle | `ContextParser[ContextT]` creates one concrete context or raises `SyntaxFailure`; other failures become tool errors |
| Rule behavior | Classes implement `RuleBundle[ContextT]`; each declares identity, API version, supported languages, and emitted rule IDs |
| Typed execution | `TypedAnalyzer[ContextT]` runs parsing before all checks and orders findings deterministically |
| Registration | `BundleRegistry` owns rule IDs; `AnalyzerRegistry` owns analyzer identities and suffixes |
| Built-in language semantics | `languages/` composes grammar, type rules, metric strategies, import extraction, and import resolution |
| Application composition | `plugins/builtins.py` registers built-ins; callers can supply an isolated registry to `engine.check`, `snapshots.sources`, and `cli.main` |

`LanguagePlugin` exposes only `analyzer()`. Custom analyzers need not use
Tree-sitter. `TypedAnalyzer` preserves the parser's exact context type through
all registered rules. Python uses `PythonContext`, which extends `TreeContext`
with `module: ast.Module | None`. The optional field represents Python AST
rejection explicitly; AST-based rules must narrow it before use. Shared tree
rules consume the existing tree view without casts. Python parses once with
Tree-sitter and once with the Python AST parser, before any rule runs.

`TreeLanguage` composes built-in syntax metrics and dependency checks. Its
`MetricSemantics`, `ImportExtractor`, and `ImportResolver` interfaces separate
language behavior from shared evaluation. Other grammars can provide their own
metric rules instead of assuming the built-in grammar node conventions.

Resolver, parser and analyzer implementations declare their protocol bases
explicitly: both import resolvers inherit `ImportResolver`, the built-in and test
parsers inherit `ContextParser[TheirConcreteContext]`, and `TypedAnalyzer` plus
the analyzer test doubles inherit `Analyzer` directly or through an implementation.
This makes the intended contract visible at the class declaration and lets mypy
check overrides. Matching method signatures alone does not establish a declared
inheritance relationship for usage analysis. Parameter reads can be shared across
the explicit family; slots unread throughout that family remain reportable.

`TypedAnalyzer` uses dataclass slots and explicit required fields for `name` and
`definition` so inherited read-only protocol properties neither become constructor
defaults nor prevent initialization. The public constructor arguments stay the same.

Parsing and recovery are parser-owned. Syntax rejection emits a `ParseWarning`
on stderr, separate from findings and checker configuration. Tree-sitter returns
its recovered context so enabled rules continue; Python AST rejection makes only
AST-based type and import checks unavailable. Warnings disclose potentially
inaccurate results. A custom parser that cannot supply any context may raise
`SyntaxFailure` with warning evidence explaining which dependent checks are
skipped; other files continue. Infrastructure exceptions still fail analysis.
If all of an analyzer's rules are disabled, the analyzer is skipped.
Registration rejects missing required rules, duplicate rule
ownership, duplicate analyzer names/languages, incompatible API versions, and
ambiguous or unusable suffixes before publishing state. Emitting an undeclared
rule or throwing an exception fails the gate. Plugin code and its declared
requirements are trusted application composition; registration does not prove
that an implementation actually enforces its declarations.

### Extending the application

A rule class declares these members:

```python
@dataclass(frozen=True)
class ModuleSizeRule:
    name: str = "project.module_size"
    api_version: int = 1
    languages: tuple[Language, ...] = (Language.PYTHON,)
    rule_ids: tuple[str, ...] = ("project.module_size",)

    def check(self, context: PythonContext) -> tuple[Finding, ...]:
        if context.module is None or len(context.module.body) <= 100:
            return ()
        return (Finding(path=context.source.path, line=1, column=1,
                        rule="project.module_size", message="Split module responsibilities"),)
```

Build the Python analyzer with `PythonLanguage().analyzer()`, register the new
object through `analyzer.bundles.register(ModuleSizeRule())`, then register the
analyzer with an `AnalyzerRegistry`. Register the other built-in analyzers in
that registry as needed. Pass the same registry to discovery and execution;
`cli.main(arguments, analyzers=registry)` does both. An injected registry is the
complete application composition, so omitting a language also omits its suffixes.
To extend a complete standard composition with a new language, start with
`builtin_registry()` and register the additional analyzer.

For a new language, construct `Language("my_language")`, a `LanguageDefinition`
with unique suffixes and nonempty required checker rules, a concrete
context/parser, and a `BundleRegistry` parameterized by that context. Compose a
`TypedAnalyzer` and register it. The executable `CounterContext` example in
`tests/test_extensions.py` proves this path with an independent grammar through
full and staged source discovery and the public CLI.

### Enforced object design

Shared orchestration must call narrow interfaces. Do not add `if`, `match`, or
`switch` dispatch on language/rule identities, global callback tables, or class
wrappers whose only purpose is to forward into a procedural dispatcher. Keep
behavior in cohesive rule/parser/strategy classes. Small private pure functions
remain appropriate for local syntax traversal and calculations.

The architecture gate provides two mechanical checks:

- `architecture.dispatch` detects comparisons of selectors named `language` or
  `rule_id` with literal identities or uppercase member constants, and
  match/switch statements on those selectors. It covers the supported Python,
  Go, Java, JavaScript, TypeScript, and TSX syntax. Comparing two runtime
  identities for compatibility is allowed.
- `architecture.object_model` rejects non-underscore module-level function declarations
  and JS/TS function-valued declarations under `checkers["architecture.object_model"].paths`
  when that checker is enabled. Methods and private underscore-prefixed pure helpers remain allowed.
  Go receiver methods are the corresponding object seam.

This repository applies `architecture.object_model.paths` to analyzers, language plugins, metrics,
and rule implementation modules. Import boundaries additionally prevent shared
analysis, registration, parsers, and rules from depending on concrete language
plugins or grammar packages. Grammar-package selection belongs in `languages/`.
The legacy `syntax.parse` facade resolves built-in tree parsers at application
composition; new plugins should use their typed parser directly.

These syntax checks cannot prove cohesion or interface conformance, detect all
aliases or indirect dispatch, or distinguish every callback bag from a legitimate
data mapping. Semantic review and mypy remain required. Per-checker enable flags are explicit policy controls; scoped exception support
is not implemented. All checkers remain enabled in this repository.

### Compatibility and validation

Built-in source suffixes, existing diagnostic IDs/messages/locations, metric
semantics, import normalization, syntax rejection, and snapshot behavior are
preserved. New architecture findings intentionally reject identity dispatch.
`Language.PYTHON` and the other named identities remain available, but `Language`
is no longer an enumerable `StrEnum`. The analyzer plugin API now declares
`definition` instead of only `language`. Procedural rule helper entry points are
replaced by the class interfaces above; `engine.check` and the CLI remain the
application entry points. The subsequent version 2 policy moves extension paths
to `Policy.checkers.architecture_object_model.paths`, which defaults to an empty
tuple. Version 1 policies must be migrated; see
[Checker configuration](checker-configuration.md).

The initial baseline audited 35 files with zero findings and passed 83 tests.
Requirement-to-test mapping:

| Requirement/risk | Behavioral evidence |
| --- | --- |
| New language without central switches | `test_new_language_runs_through_cli_and_discovery` |
| Rule extension preserves a concrete AST | `test_new_rule_extends_builtin_without_engine_dispatch` |
| Parse once; warnings permit available checks | `test_custom_context_is_parsed_once_for_all_rules`, custom syntax cases, Python AST rejection, `test_syntax_warnings.py` |
| Staged custom suffixes preserve exact input | `test_custom_language_staged_selection_preserves_snapshots` |
| Plugin failures do not pass | CLI parser failure and undeclared rule/analyzer output tests |
| Registration rejects ambiguity atomically | conflicting suffix test and invalid metadata parameterizations |
| Stable finding order | `test_findings_are_sorted_independently_of_registration_order` |
| Class/interface architecture policy | cross-language cases in `test_object_design.py` and public CLI policy test |
| Existing contracts, metrics, dependencies, and read-only behavior | retained gate, metrics, and CLI regression suites |

No type exceptions, scope exclusions, or metric-limit increases are introduced.


#### Delivery evidence

Validation on 2026-09-28:

| Command | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` | 45 files, zero findings |
| `uv run --no-sync mypy src tests` | Passed, 44 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed, 45 files |
| `uv run --no-sync pytest -q` | 145 passed |
| `git diff --check` | Passed |

Coverage was measured with an isolated `coverage==7.13.4` tool, without changing
project dependencies or the lockfile:

```sh
uv run --no-sync --with coverage==7.13.4 python -m coverage run --branch --source=code_harness --data-file=/tmp/code-harness-plugin-final.coverage -m pytest -q
uv run --no-sync --with coverage==7.13.4 python -m coverage report --data-file=/tmp/code-harness-plugin-final.coverage -m
uv run --no-sync --with coverage==7.13.4 python -m coverage xml --data-file=/tmp/code-harness-plugin-final.coverage -o /tmp/code-harness-plugin-final.xml
```

The full runtime has 1,028/1,060 covered statements (97.0%) and 269/292 covered
branches (92.1%). Comparing XML executable lines with the current Git diff and
new source files gives 538/546 changed executable lines (98.5%) and 116/120
branches originating on changed lines (96.7%). The typed analyzer, both
registries, language composition, and object-design rule have complete executable
line and branch coverage.

Inspected changed misses are the legacy architecture/import export facades,
the unknown-language error in the legacy tree-parser facade, extensionless
relative-import resolution, filtering nonselected changed paths, unresolved
literal imports, and the defensive discovery-registration consistency error.
Retained gaps include unusual Python annotation forms, grammar helper branches,
and filesystem/Git errors. These remain visible; coverage is not represented as
complete. The architecture review confirmed canonical source/context contracts,
concrete context propagation, parser-owned syntax rejection, rule-owned behavior,
atomic registry state publication, and composition-only concrete grammar imports.
The syntax checks' alias/indirect-dispatch and semantic ownership limits described
above remain review obligations.


### Agent review extension

Prompt-owned semantic review rules implement `AgentReviewRule` and register through
the same typed rule registry. `AcpReviewAgent` invokes an explicitly configured
ACP executable and registers MCP tools for incremental finding submission and
explicit completion. See [Agent review rules](agent-review.md) for interfaces,
composition, transport boundaries, and verification scope.

### Checker configuration and execution

Each logical checker owns a concrete options field under `Policy.checkers`.
`FunctionSizeOptions` owns the five function metric thresholds and one enable flag.
Owner, import, and object-model settings remain independent. The policy projects
enable flags into a set of disabled IDs
without widening its concrete option types. Shared registries consume this set
without importing language implementations or interpreting checker-specific data.

A bundle whose diagnostics are all disabled is never invoked. Bundles that still
own enabled diagnostics may share parsing and traversal work; only enabled
findings are returned. Bundle output validation still rejects undeclared findings,
and failures in an executing bundle remain errors. Registration continues to
require the language's complete rule contract regardless of current enable flags.
Standalone custom analyzers receive the policy and must preserve parser failure
semantics; the analyzer registry also filters explicitly disabled built-in IDs.

Custom rule-specific configuration remains owned by plugin construction, including
agent-review prompts and transport settings. The JSON `checkers` schema covers the
11 logical checker names controlling 15 built-in diagnostic IDs and rejects
unknown checker names and misplaced options. The configuration key `function_size`
expands to all five `size.*` diagnostic IDs for execution; reports name the disabled
logical checker. Omitted checker entries remain enabled with default options.


### Cross-file usage evidence

Built-in languages register a concrete `SemanticParser` alongside their analyzer
in `AnalyzerRegistry`. The parser pairs the language grammar with its
`SemanticSyntax` strategy; shared resolution never dispatches on language names.
`analyze_sources` checks selected sources normally, then replaces usage findings
with results linked across the supplied reference snapshots. Other diagnostics
retain their existing rule-bundle ownership and checker filtering. Single-source
plugins keep working without a project semantic registration.

The `semantics` package owns declaration identity, lexical scopes, field reads,
external-use evidence and project linking. Language strategies own imports,
parameter grammar, public entry points and package identity. Snapshot selection
continues to belong to infrastructure, including unchanged index references in
staged mode. Findings keep the canonical diagnostic contract and their new
`error`/`warning` severity; only errors determine CLI defect exit status.


## Alias and output generalization validation

On 2026-10-08, all 760 tests passed after extracting the shared alias and value-flow
engines. The existing Python JSON and third-party regression cases remain passing;
132 additional JS/TS/TSX cases exercise internal carriers, stable callable/module
aliases, cycles, shadowing, terminal/filesystem outputs, decoder round trips,
configured library inputs and the `type.broad` switch through registered analyzers.
`uv run --no-sync mypy src tests`, `uv run --no-sync ruff check src tests`,
`uv run --no-sync ruff format --check src tests`, and `git diff --check` passed.
The full `uv run --no-sync code-harness --all` audit checked 122 files with zero
errors and 45 discarded-return warnings. No policy exclusions or thresholds changed.
These results do not establish changed-line/branch coverage or Go/Java serializer
recognition.
