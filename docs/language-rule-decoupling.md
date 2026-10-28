# Decouple language parsing and rule policy

Status: approved architecture implemented as extension API 2; independent review
and final validation are recorded below. The initial documentation/policy-only
audit is retained as historical evidence.

This design supersedes the language-owned composition and dual-parser direction
in the historical [pluggable analysis plan](pluggable-analysis-plan.md).
[Plugin architecture](plugin-architecture.md) documents API 2 and retains the prior
API 1 reference separately. The implementation introduces no type exceptions,
scoped waivers, checker disabling or source exclusions.

## Target ownership

All language parsers produce one concrete tree-sitter context. Tree-sitter provides
a common tree API, but node kinds, named fields and semantics remain grammar
specific. Keep the original tree and provide typed interpretation where rules
need shared concepts. Shared rules do not inspect language identities.

| Component | Responsibility |
| --- | --- |
| Language plugin | Identity, suffixes, grammar and language syntax adapters |
| Parser | Tree-sitter parsing, source locations and recovery diagnostics |
| Grammar adapters | Interpret functions, parameters, control flow, imports, bindings and type constructs |
| Shared analysis | Metric calculation, scope/reference resolution and boundary evidence |
| Rules | Policy decisions, thresholds and findings |
| Application composition | Register languages and rules independently; connect capabilities and validate required coverage |
| Analysis session | Own exact source snapshots, trees, reusable evidence and mutable project resolution |

The intended flow is source snapshot -> tree-sitter tree -> typed syntax facts ->
shared analysis -> rules -> findings. A syntax-only rule can consume tree evidence
directly. A grammar-specific rule can interpret its own grammar. Shared rules must
not accumulate language node-name switches as additional grammars are introduced.

Language plugins stop implementing `analyzer()` as a composition operation.
Move analyzer assembly from `languages/tree.py` and `languages/python.py` to
`plugins/builtins.py`. Move `LanguageDefinition.required_rules` into an
application-owned analysis profile. Identity and suffix discovery remain language
responsibilities. Enabled checks remain governed by `Policy.checkers`; required
coverage is validated independently of enable flags.

## Approved source structure

The implemented layout separates grammar interpretation, shared analysis and
policy execution. Package initializers, compatibility exports and unchanged
transport files are omitted for readability. The API 2 compatibility changes are
documented in the plugin guide.

```text
src/code_harness/
  source.py                     Source snapshots, language identity and suffixes
  diagnostics.py                Findings, warnings and analysis failures
  parsing/
    treesitter.py               Shared parser lifecycle and grammar-neutral traversal
  analysis/
    context.py                  One concrete tree-sitter context for every language
    contracts.py                Parser/rule/analyzer execution protocols
    requirements.py             Typed rule capability requirements
    analyzer.py                 Execute composed rules and order findings
    session.py                  Snapshot trees, reusable evidence and resolution lifetime
  plugins/
    languages.py                Language plugin contract and identity/suffix registration
    bundles.py                  Register rule objects and diagnostic ownership
    profiles.py                 Required coverage and optional-analysis disclosure
    registry.py                 Validate and expose composed analyzers
    builtins.py                 Assemble built-in languages, profiles and rule objects
  languages/
    python/
      plugin.py                 Python identity, suffixes and grammar
      syntax.py                 Python metrics and import interpretation
      semantic_syntax.py        Python binding, visibility and type syntax
      type_syntax.py            Python qualified names, aliases and expression use
      rules.py                  Python-specific annotation, escape and JSON checks
    go/
      plugin.py                 Go identity, suffixes, grammar and terminal newline handling
      syntax.py                 Go grouped parameters and imports
      semantic_syntax.py        Go receivers, packages and binding syntax
      rules.py                  Go-specific interface and type checks
    javascript/
      plugin.py                 JavaScript/JSX identity, suffixes and grammar
      syntax.py                 JS-family metrics, imports and relative resolution
      semantic_syntax.py        JS-family bindings, exports and type syntax
    typescript/
      plugin.py                 TypeScript and TSX registrations and grammars
      syntax.py                 Typed/JSX syntax differences; reuse JS adapters where valid
      rules.py                  TypeScript assertion and type-specific checks
    comments.py                 Common comment syntax for suppression checks
    metric_syntax.py             Reused grammar measurement operations
    import_syntax.py             Reused literal dependency extraction
    design_syntax.py             Grammar interpretation for object-design policy
    semantic_nodes.py            Reused grammar interpretation behind semantic protocols
    type_checks.py              Shared execution of language-specific type markers
  metrics/
    contracts.py                Canonical Metrics and narrow function/control syntax protocols
    measure.py                  Shared calculations over typed syntax facts
    rules.py                    Shared function-limit policy
  architecture/
    models.py                   Canonical dependency evidence
    imports.py                  Import extraction/resolution contracts
    design_contracts.py         Narrow object-design syntax contract
    design.py                   Shared object-design policy
    rules.py                    Ownership, placement and dependency restrictions
  semantics/
    model.py                    Canonical symbols, scopes, usage evidence and syntax contracts
    index.py                    Shared lexical declaration and reference resolution
    project.py                  Cross-file linking over session-owned evidence
    overrides.py                Override-family usage propagation
    boundaries.py               Third-party boundary evidence and policy
    usage.py                    Shared unused-declaration and discarded-result policy
  suppressions.py               Shared suppression policy over supplied syntax evidence
  policy/
    models.py                   Validated checker options and repository policy
    paths.py                    Policy path matching
  review/                       Existing semantic-review rules and transport ownership
  engine.py                     Application analysis entry point
  snapshots.py                  Filesystem/Git snapshot selection
  cli.py                        CLI orchestration and reporting
```

Shared rules stay with the domain whose policy they enforce: metrics under
`metrics/`, dependency checks under `architecture/`, usage and boundary checks
under `semantics/`. Language-specific rules stay alongside the owning grammar.
There is no root catch-all rule package. A `syntax.py` module may contain several
cohesive adapter classes implementing different consumer-owned protocols; it must
not become a single interface exposing every language operation.

`plugins/profiles.py` owns application composition requirements, not grammar or
checker options. `plugins/languages.py` owns discovery registration, while
`plugins/bundles.py` owns rule registration. `plugins/builtins.py` is where concrete
adapters and rule implementations meet. Required rule sets move out of language
identity objects. Application composition binds concrete capability implementations
through typed interfaces, with no arbitrary capability dictionary.

Dependency direction follows those owners:

- Language plugins use parsing and domain syntax contracts; they do not assemble
  analyzers or select the shared rule set.
- Shared analysis and rules consume those contracts; they do not import concrete
  language plugins. For example, `languages/python/syntax.py` implements a metric
  syntax protocol from `metrics/contracts.py`, and `metrics/measure.py` consumes it.
- Application composition imports concrete languages and rules. The session and
  analyzer execute the resulting typed composition without identity dispatch.
- CLI and snapshot infrastructure remain outside domain analysis. Existing review
  rule/transport boundaries remain independent of this migration.

### Migration from the API 1 layout

| Former responsibility | Implemented destination or transition |
| --- | --- |
| `languages/tree.py` and language `analyzer()` methods | Assembly in `plugins/builtins.py`; requirements in `plugins/profiles.py` |
| Language identities, grammars and suffixes in `languages/*.py` | Each language's `plugin.py` |
| `languages/semantic_syntax.py` | Owning language's `semantic_syntax.py`; shared JS-family interpretation in `languages/javascript/semantic_syntax.py`; consumed compatibility exports retained |
| `metrics.py` | Contracts, shared measurement and policy under `metrics/`; Python/Go grammar strategies move to their syntax adapters |
| Grammar extraction in `architecture/imports.py` and `architecture/design.py` | Language syntax adapters; retain shared contracts and policy with architecture |
| Grammar cases in semantic indexing, usage and boundary analysis | Language adapters expose facts; shared resolution and policy remain under `semantics/` |
| `languages/python_rules.py` | `languages/python/rules.py`, ported to the common tree context |
| Go and TypeScript checks in root `rules.py` | `languages/go/rules.py` and `languages/typescript/rules.py` |
| Shared suppression detection in root `rules.py` | `suppressions.py`, with grammar interpretation supplied by adapters |
| `parsing/python.py` and `PythonContext.module` | Retired after migrating Python consumers; tree-sitter owns parsing |
| `GoParser` in `parsing/treesitter.py` | Go-owned parser specialization alongside its plugin |
| Reparsing in `SemanticParser` and repeated rule-local indexes | Session-owned tree/evidence lifetime in `analysis/session.py` |

Canonical contracts move to their new owners rather than being copied.
Compatibility facades (`syntax.py`, `imports.py`, `models.py` and `architecture.py`)
retain consumed exports. The old grammar-aware `walk(skip_functions=...)` contract
is replaced by grammar-neutral traversal; language adapters own pruning. Language
syntax modules are split only where a distinct responsibility warrants it.

The repository policy follows the new paths. `metrics/*` has its own owner and
shared import restrictions; nested language packages remain covered by
`languages/*`. Language-specific rule placement also names nested `rules.py`
modules. Full source selection and existing checker limits remain unchanged.

## Tree and capability contracts

Converge on the existing `TreeContext` responsibility while retaining a concrete
`tree_sitter.Tree` and its `Node` evidence for the analysis lifetime. Remove the
Python-only `ast.Module` context after migrating its consumers. All language
plugins, including external extensions, use the tree-sitter parsing contract in
the target design. The current generic `ContextParser` and non-tree test plugin
are historical API 1 interfaces. API 2 intentionally removes arbitrary context
type parameters; the replacement count-dialect extension tests use tree-sitter
and verify registration, discovery, CLI execution and snapshot preservation.

Introduce narrow consumer-owned protocols as needed, rather than one large
language service. Concrete adapter implementations belong under `languages/`;
their shared contracts belong to the domain consuming the facts. For example:

- Function and control-flow syntax expose bodies, explicit parameter bindings,
  decisions and nesting relationships needed by metrics.
- Import syntax exposes dependency evidence and module resolution conventions.
- Binding syntax exposes declarations, references, scopes, receivers and visibility.
- Type syntax exposes supported annotation and assertion constructs.

Preserve concrete types through these boundaries. Reuse `Import`, `ImportedName`,
`Symbol`, `Scope` and `Metrics` where their existing meaning fits; introduce a new
contract only for distinct facts or lifecycle invariants. Facts retain source-node
evidence. Do not flatten the tree into JSON, create a second universal AST, erase
types or transport capabilities through a heterogeneous dictionary and casts.

Rules declare the typed capabilities they need instead of enumerating supported
languages. Application composition binds concrete adapters to those interfaces.
Only genuinely language-specific rules need an explicit applicability binding at
composition. `RuleRequirements` declares semantic evidence demand; metric, import
and design adapters are supplied through their concrete protocol contracts.
`AnalysisProfile` owns required coverage and names unavailable optional analyses,
which are disclosed through warnings. No heterogeneous capability registry exists.

Registration must reject missing required capabilities, conflicting diagnostic
ownership within one composed execution, invalid API versions and ambiguous
suffixes. Optional unavailable analysis must be disclosed separately from a clean
result. Missing required registration and infrastructure failures remain errors;
syntax recovery remains a distinct, explicitly qualified outcome.

## Shared behavior and language exceptions

| Shared policy or algorithm | Grammar-specific evidence or behavior |
| --- | --- |
| Function limits | Function boundaries, decisions, grouped parameters, receivers and docstrings |
| Ownership and import restrictions | Import syntax, dependency names and resolution conventions |
| Unused declarations/results | Binding, visibility, override relationships and return semantics |
| Concrete-type requirements | Python annotations, Go interfaces and TypeScript assertions |
| Suppression prohibition | Comment directives and language-specific decorators |

For example, Go expands grouped parameters into individual explicit bindings;
Python identifies implicit receivers. One shared metric algorithm counts the
appropriate bindings and one rule compares that count with the configured limit.
Neither shared component selects a language identity.

Keep Python forward annotations, Go capability interfaces and TypeScript assertion
syntax with their language owner. Share policy when its meaning is shared; retain
separate rule classes where language semantics justify them. Move the existing Go
and TypeScript type rules out of root `rules.py` as part of runtime migration.
Language-specific checks and adapters may consume shared contracts and evidence,
but analyzer assembly and selection of rule bundles belong to composition.

## Session ownership and recovery

Parse each exact snapshot once per analysis session and reuse its tree for local
rules and project analysis. Snapshot identity includes content and grammar, not
just a path, so staged and working-tree sources cannot share stale evidence.
Build reusable syntax facts once when needed. One session-owned resolution phase
owns mutable scope, reference and boundary state; rule order must not affect
findings. Do not cache mutable indexes globally or share them between sessions.

The former `SemanticParser` reparsing path and rule-local index construction are
replaced by session-owned trees and semantic evidence. Registration attaches each
analyzer's typed semantic binding automatically. Evidence is prepared only when
an enabled rule needs it, while capability validation remains unconditional.
Project resolution produces immutable `UsageEvidence`; only registered usage
rules apply policy to those facts. The registry does not inject usage diagnostics.
Python forward annotations parse distinct embedded expressions using tree-sitter;
this does not reparse the whole source snapshot.

Selected source snapshots take precedence over references with the same language
and path. Conflicting contents for one semantic module in the same execution are
rejected explicitly. Sessions reject a different policy, cache syntax rejection
and normalize parser/semantic preparation failures into tool errors.

Retain parser-owned recovery warnings and best-effort tree checks. Individual
analyses must represent insufficient evidence explicitly. Porting Python checks
must review differences between CPython AST rejection and tree-sitter recovery,
including forward annotations, type comments, aliases and error-node locations.
Do not promise identical parser acceptance. Preserve diagnostic behavior for
supported valid inputs; document and test deliberate recovery changes.

## Repository gate and review limits

The active `.codeharness/code-harness.json` adds two import boundaries using the
existing version 2 schema and `architecture.import` checker:

1. Runtime source under `src/*` cannot import `ast` or its members. Python type,
   import and forward-annotation checks now consume tree-sitter evidence.
2. Modules under `languages/*` cannot import analyzer construction, bundle/analyzer
   registries, built-in composition or listed concrete shared rule evaluators.
   Shared contracts remain available; analyzer assembly lives in application
   composition.

Owners and import selectors follow moved files. Existing selection, enabled
checkers and limits remain in force. No source paths
are excluded and no diagnostics are suppressed to make migration debt pass.

These import checks do not prove that every parser uses tree-sitter, all rules
consume one context, facts retain types, or parsing occurs once. They do not detect
constructor calls through every alias or prohibit grammar-specific node names in
shared code. The targeted evaluator import list must be maintained as evaluators
change; module imports with attribute access can evade symbol-level entries.
Canonical ownership, correct grammar interpretation and state lifetime continue
to require semantic review; import checks alone do not prove them.

Python import extraction now uses the recovered tree, so a CPython AST rejection
no longer removes dependency evidence from an otherwise usable tree. Recovery
remains best-effort and import-policy success cannot establish full conformance.

## Migration and acceptance

1. Separate language registration and rule composition without altering execution.
2. Port Python type/import checks to tree-sitter and converge on one context;
   make extension compatibility changes explicit.
3. Extract grammar interpretation from metrics and imports, then semantic analysis;
   bind shared rules through narrow typed capabilities.
4. Consolidate session-owned parsing and evidence, update dependency policies and
   audit the resulting call chains before declaring conformance.

Required behavioral evidence for this implementation:

| Requirement or risk | Acceptance evidence |
| --- | --- |
| Shared policy across grammars | The same metric/import rule runs through distinct adapters with equivalent results |
| Independent registration | A new grammar and a new shared rule need no engine or language-identity dispatch |
| Capability availability | Missing required capabilities fail; optional unavailable analysis is disclosed |
| Concrete contracts | Strict typing passes without casts, broad carriers or reconstructed payloads |
| Parse and state ownership | One parse per snapshot; local/project reuse; no stale evidence or order-dependent findings |
| Python migration | Assertions cover annotations, aliases, forward types, imports, boundaries and syntax recovery |
| Compatibility | Finding IDs, messages, locations, ordering, disabled checks and snapshot selection remain covered |
| Read-only execution | Source and Git state remain unchanged by gate execution |

Run the full self-audit, mypy, Ruff lint/format checks and pytest at each completed
phase. Record changed-line and branch coverage for implementation changes. The initial
documentation-only validation below is historical; current implementation evidence
is recorded separately.

## Historical documentation-only review evidence

Validation on 2026-09-30, with runtime and test sources unchanged:

| Command | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` before policy changes | Exit 0; 73 files, zero errors and 34 existing warnings |
| `uv run --no-sync code-harness --all` after policy changes | Exit 1; 73 files, 26 architecture import errors and the same 34 warnings |
| `uv run --no-sync mypy src tests` | Passed; 72 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed; 73 files |
| `uv run --no-sync pytest -q` | 440 passed |
| `git diff --check` | Passed |

The new errors comprise four `ast` dependency findings and 22 composition
findings across `languages/python.py` and `languages/tree.py`. The import extractor
reports both module and member dependencies for some imports, so the 26 errors
are not 26 independent import statements. Six runtime files are affected.
At that documentation-only stage the full gate failed, including CI using the
repository policy. That historical result is superseded by implementation
validation below.

Six additional in-memory checks through `engine.check` and the actual repository
policy verified rejection of aliased `ast`, `from ast import Module`, nested
language-module analyzer imports and concrete metric-rule imports; shared metric
contracts and analyzer imports at application composition remained accepted.
No fixture or test source files were added. A typed policy comparison against
HEAD verified unchanged include/exclude patterns, third-party configuration,
checker switches, function limits, ownership, placement, object-model paths and
all pre-existing import boundaries.

Architecture review confirmed that the new policy restricts parser dependencies
and composition direction without relocating canonical contracts or widening
concrete types. Existing grammar logic, Python-only contexts, capability selection
and mutable index ownership remain explicit implementation debt. No type
exceptions, rule waivers or source exclusions were introduced. This evidence
validates the documentation and policy scope only.


## Implementation review

Implementation was delegated to a subagent and independently reviewed against the
approved ownership boundaries and a preserved pre-refactor source snapshot.
Review corrections cover automatic semantic binding during registration,
normalization of semantic preparation failures, unconditional capability checks,
session policy consistency, selected-source precedence over stale references,
and evidence preparation only for enabled consumers. Shared suppression policy
now receives comment/decorator syntax through adapters; Python alias interpretation
has one language-owned implementation.

The review also reproduced project analysis emitting unused-code diagnostics for
an analyzer that registered only suppression checks. Project resolution supplies
reusable usage evidence to registered rules; it must not select or execute a
usage rule itself. The extension regression compares local and project execution
for that restricted composition.

| Requirement or risk | Observable regression evidence |
| --- | --- |
| Common context and independent extensions | `test_one_rule_consumes_the_same_context_across_grammars`; CLI/discovery and staged snapshot tests in `test_extensions.py` |
| Required capabilities and explicit optional absence | Late semantic requirement rejection, optional-unavailable warnings and invalid profile tests |
| Exact parse lifetime | Duplicate snapshots parse once, later executions parse afresh, same-path byte variants remain distinct, syntax rejection emits one warning |
| Composition controls execution | Disabled semantic consumers do not prepare evidence; semantic capability alone does not enable unregistered usage rules |
| Failure ownership | Parser/plugin failures and semantic preparation failures reach the CLI as tool errors; mismatched session policies fail |
| Python tree migration | `test_python_tree_rules.py` covers aliases, forward annotations, escaping, Unicode columns, receiver/signature handling and recovered syntax |
| Shared resolution | Semantic and override tests exercise imported declarations, inherited fields and usage propagation across implementations |
| Diagnostic compatibility | Independent baseline comparison covers annotations, imports, boundaries, metrics and cross-file/repeated executions |

The independent comparison uses 60 source cases and four project executions, with
exact finding IDs, messages, locations and ordering compared to the preserved
implementation. Its temporary corpus and original snapshot are retained under
`/tmp/code-harness-review-ZdHM85` for this review; committed regression tests are
the durable evidence. Parser warnings intentionally differ where Python formerly
ran a second CPython AST parser.

Extension API 2 is a deliberate compatibility change; the policy schema remains
version 2. Syntax recovery remains best-effort. Resolution retains the existing
limits for dynamic imports, external types, aliases and compiler-only semantics.
The architecture gate cannot prove these semantic properties by import checks
alone. A typed policy comparison against HEAD verifies unchanged file selection,
exclusions, third-party configuration, enabled diagnostics and function limits.
Ownership and dependency selectors follow the new module locations. No type
exceptions, disabled checks or source exclusions were introduced.


## Final implementation validation

Independent validation on 2026-09-30 after the review corrections:

| Command or comparison | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` | Exit 0; 102 files, zero errors and the same 34 baseline warning-only findings |
| `uv run --no-sync mypy src tests` | Passed; 101 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed; 102 files |
| `uv run --no-sync pytest -q` | 509 passed |
| Independent pre-refactor diagnostic comparison | Exact match across all 64 output records |
| `git diff --check` | Passed |

All checks were read-only. No dependency or lockfile changes were needed. The
original implementation snapshot remains available for review. Changes are left
uncommitted; these results do not imply publication or deployment.


Coverage was measured over `src/code_harness` with branch tracking using the
project interpreter and an existing Coverage.py 7.13.4 installation exposed from
`/tmp/code-harness-coverage-tool` (`COVERAGE_CORE=pytrace`). The coverage test run
also passed all 509 tests.

| Coverage scope | Covered / total | Rate |
| --- | --- | --- |
| Production statements | 3,107 / 3,193 | 97.31% |
| Production branches | 911 / 990 | 92.02% |
| Changed executable lines | 1,708 / 1,740 | 98.16% |
| Branches originating on changed lines | 537 / 574 | 93.55% |

Changed coverage uses added lines from `git diff HEAD --unified=0 --no-renames`
plus all untracked production source files, intersected with executable coverage
lines and branch origins. This includes moved implementations as new source,
not just newly authored behavior. There are 67 partially covered branches across
production code. Evidence is retained in
`/tmp/code-harness-refactor-coverage.json`; the typed calculation script is
`/tmp/summarize_refactor_coverage.py`.

Missing changed lines and branches were reviewed. They include absent-evidence
fail-fast guards, pass-through analysis errors, reuse of an already prepared
index, unusual malformed forward-string/type syntax, unresolved receiver/member
paths, dynamic field introduction and typed-return boundary evidence. These
remain coverage limitations; the percentages do not establish complete semantic
conformance. The semantic syntax-rejection path has a regression verifying one
parse and one warning across preparation and repeated execution.
