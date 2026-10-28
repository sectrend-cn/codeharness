# Boundary and usage validation — 2026-09-29

The automatic checks cover Python, Go, JavaScript/JSX and TypeScript/TSX. The
approved exception follows data direction: dictionaries supplied to configured
libraries, including callback returns, may erase value types at the boundary.
Library results and callback inputs retain or acquire concrete contracts at ingress.
The gate reports unused parameters/functions/fields and warns on discarded results.
See [configuration and limits](checker-configuration.md#third-party-boundaries-and-usage).

## Ownership and architecture review

The `semantics` package owns lexical declarations, class identity, read/write
tracking, library-boundary evidence and cross-file linking. Language strategies
own parameter grammar, import bindings, package identity and externally visible
entry points. The registry composes these strategies without language-name
switches. Snapshot infrastructure retains source selection and exact index reads;
analysis receives immutable source bytes and never writes source or Git state.

Canonical `Finding` and `Report` contracts carry severity and reference scope.
`Symbol`, `Scope` and import contracts retain concrete syntax types throughout.
No casts, generic JSON carriers, source suppressions or implementation comments
were introduced. Review transport contracts continue using the canonical findings.

Repository policy adds the semantic package to the existing rule owner,
dependency boundaries and object-model paths. It explicitly identifies `pydantic`
as third-party code for metaclass-consumed model declarations. All checkers remain
enabled, limits are unchanged and no sources are excluded to hide new findings.

## Initial verification before override-family analysis

| Command | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` | Exit 1: 69 files, 14 unused-parameter errors and 34 return warnings |
| `uv run --no-sync mypy src tests` | Passed, 68 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed, 69 files |
| `uv run --no-sync pytest -q` | 345 passed |
| `git diff --check` | Passed |

The initial isolated-body analysis reported 14 unread parameters in import/metric
strategies and test doubles or fixtures. It incorrectly reported parameter slots
read by related overrides as unused. The override correction below supersedes
that result; existing implementations remain unchanged.
Warnings include meaningful results ignored by existing callers and test helpers;
warning-only audits return zero. No other checker produced a final audit finding.
The complete local text report is `/tmp/code-harness-usage-final-audit.txt`.

## Requirement and risk coverage

- Grammar-specific tests cover parameters, private functions, field reads/writes,
  outbound object use and discarded returns across all supported language families.
- Boundary tests cover forwarding dictionaries/kwargs, reversed callback direction,
  typed callback conversion, raw results, internal callback callers, module aliases,
  shadowed imports, CommonJS bindings and nullable concrete SDK specializations.
- Ownership tests distinguish same-named fields, nested class names, closures and
  block shadows. Cross-file tests cover relative imports and Go package references.
- CLI tests prove warning-only exit status, independent checker switches and
  unchanged staged consumers read from the index despite broken working copies.
- Protocol and external metaclass tests prevent implementation methods or
  framework-owned field metadata being misreported as unused or erased results.

Branch coverage used cached `coverage==7.13.4` in an isolated offline uv environment:

```sh
COVERAGE_FILE=/tmp/code-harness-usage-final.coverage \
uv run --offline --no-sync --with coverage==7.13.4 coverage run --branch \
  --source=code_harness.semantics,code_harness.languages.semantic_syntax \
  -m pytest -q tests/test_semantic_usage.py tests/test_cli.py tests/test_checker_options.py
```

All 149 targeted cases passed. The new semantic implementation covers **816/877
statements (93.04%)** and **353/414 branches (85.27%)**. XML evidence is
`/tmp/code-harness-usage-final-coverage.xml`. Remaining gaps include uncommon
namespace/import forms, inherited and iterated receiver paths, syntax-recovery
exits and partial branches in return-discard recognition. Coverage is not a claim
of complete type inference or whole-program dead-code proof. Exported APIs,
unresolved dynamic receivers and external consumers retain the documented
conservative treatment and semantic-review obligations.


## Override-family correction — 2026-09-29

An interface parameter is used when a corresponding parameter is read in an
implementation of the same resolved inheritance contract. `OverrideUsage` owns
that propagation over the existing canonical scopes and symbols, retaining actual
source reads separately. Positional slots match by position, keyword-only slots
by name, and variadic slots by kind. Base, sibling and transitive implementations
share evidence, including imported bases and JS/TS `extends` relationships.
Constructors and unrelated methods do not share slots; extra parameters and slots
unread throughout the family still produce findings. Structural protocols without
resolved inheritance retain their documented inference limit.

The `StandardMetrics`/`PythonMetrics`/`GoMetrics` regression checks the actual
repository source and confirms that its shared `node` and `source` parameters no
longer produce false positives. Additional tests cover reverse usage propagation,
unread entire families, unrelated classes, extra arguments, positional renaming,
keyword-only reordering, variadics, constructors and cross-file reference scope.

| Command | Corrected result |
| --- | --- |
| `uv run --no-sync code-harness --all` | Exit 1: 71 files, 8 remaining parameter findings and 34 return warnings |
| `uv run --no-sync mypy src tests` | Passed, 70 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed, 71 files |
| `uv run --no-sync pytest -q` | 359 passed |
| `git diff --check` | Passed |

The corrected report is `/tmp/code-harness-override-final-audit.txt`; the original
report remains available for comparison. No finding concerns `metrics.py`, and
no checker has been disabled. The remaining parameter findings require separate
review, including structural interface relationships not resolved by inheritance.

Coverage over `code_harness.semantics.overrides` with the override and existing
semantic tests passed 94 cases, covering **91/91 statements** and **43/44 branches**.
The one uncovered branch skips a superclass that does not define the method being
examined. Evidence: `/tmp/code-harness-override.coverage` and
`/tmp/code-harness-override-coverage.xml`, using the same cached offline coverage
tool described above. The new owner stays in the existing semantic package and
policy boundaries; no source selection, typing exception or gate threshold changed.

## Review of the eight remaining parameter findings

This records the intermediate review before the explicit protocol links below.

The two `store` parameters in `test_tool_methods_return_only_small_receipts` and
`test_tool_bounds_message_size` now use `pytest.mark.usefixtures("store")` instead.
The fixture still creates `scope.json` before `ReviewSubmissionServer` opens it;
only the unread fixture result binding is removed.

The remaining six findings are valid unread parameters, retained for these
specific call contracts:

| Method | Unread parameters | Decision and caller evidence |
| --- | --- | --- |
| `LiteralImportResolver.names` | `source` | Retain: `ArchitectureRule._forbidden` calls the shared `ImportResolver` signature with dependency and source. Relative resolution needs the source path; literal identities do not. |
| `CounterParser.parse` | `policy` | Retain: `TypedAnalyzer.analyze` passes source and policy through `ContextParser`. The count-only grammar has no policy-dependent parsing. |
| `BrokenCounterParser.parse` | `source`, `policy` | Retain: the same parser call must reach the intentional infrastructure failure before either input is processed. |
| `_FailingAnalyzer.analyze` | `policy` | Retain: `AnalyzerRegistry.analyze` passes both inputs through `Analyzer`. The test double raises immediately. |
| `_UndeclaredAnalyzer.analyze` | `policy` | Retain: the registry calls the same signature to test undeclared findings. Both it and its base ignore policy, so explicit inheritance supplies no read evidence. |

Structural compatibility and caller requirements do not establish parameter read
usage under the current rule. Removing these parameters individually would break
the shared calls; changing the shared APIs would affect production parsers,
resolvers and independently registered plugins. Method docstrings record the
constraints. No artificial reads, additional inheritance, suppressions or checker
exceptions were introduced. The six findings remain errors requiring an explicit
future API or policy decision, rather than being classified as false positives.

The full audit now checks 71 files and exits 1 with six unused-parameter errors
and 34 return warnings. Mypy, Ruff lint and Ruff formatting checks pass.
The full pytest suite passes all 359 tests, including both fixture setup cases;
`git diff --check` also passes.

## Explicit resolver, parser and analyzer protocol links

The user requires intended interface relationships to be declared explicitly.
`LiteralImportResolver` and `RelativeImportResolver` now derive from
`ImportResolver`. `PythonParser`, `TreeParser`, `CounterParser` and
`BrokenCounterParser` derive from `ContextParser` with their exact context types.
`TypedAnalyzer` and `_FailingAnalyzer` derive from `Analyzer`;
`_UndeclaredAnalyzer` inherits that contract through `_FailingAnalyzer`.

The earlier decision to stop at signature documentation is superseded. Reads in
`RelativeImportResolver`, the production parsers and `TypedAnalyzer` now supply
actual evidence within declared families for all six remaining parameter slots.
The checker logic and configuration are unchanged. No structural matching,
artificial reads, broad type substitutions or suppression mechanisms were added.
The earlier pytest fixture marker fixes remain in place.

Ownership remains with the existing architecture, parsing, analysis and test
modules. Parsers depend on the shared contract module, which depends only on
context, diagnostic, policy and source contracts; it does not import parsers.
No dependency boundary changes or new modules are required. `TypedAnalyzer`
retains its constructor signature and uses explicit required dataclass fields
with slots to implement the inherited metadata properties safely.

Regression tests verify that generic protocol implementations share actual reads,
unlinked structural matches remain reportable, slots unread across an entire
family remain reportable, and an imported generic protocol connects a selected
implementation to a reader in another file. Existing extension tests exercise
analyzer construction, custom parsing, parser failures and invalid plugin output.

| Command | Result after explicit links |
| --- | --- |
| `uv run --no-sync code-harness --all` | Exit 0: 71 files, zero errors and 34 existing return warnings |
| `uv run --no-sync mypy src tests` | Passed, 70 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed, 71 files |
| `uv run --no-sync pytest -q` | 362 passed |
| `git diff --check` | Passed |

The final audit report is `/tmp/code-harness-explicit-protocol-audit.txt`.

## Call-specific generic results (2026-10-15)

`unused.return` now queries a concrete `ResultKind` through the language semantic
capability before using the existing declaration fallback. `semantics/results.py`
owns result states, recursion guards and snapshot ownership; the JavaScript,
TypeScript and Python language owners interpret callback and generic syntax.
Go and Java retain their declaration fallback because empty structs and boxed
`Void` are value results. Existing ownership and dependency policy covers these
modules without configuration changes. No suppression or type-erasure exception
was introduced.

The regression cases in `test_generic_results.py` cover void/None callbacks,
explicit and inferred generic arguments, declared callback contracts, concrete
values, mixed return paths, async/generator and wrapped results, methods,
reassignments, overloaded/shadowed contracts and unresolved evidence.
`test_generic_result_snapshots.py` covers imported TypeScript and Python methods
and callbacks, full/changed/staged audits, unstaged signature/body changes and
fresh evidence after a staged signature change. `test_line_suppressions.py`
verifies exact next-line filtering and stale suppression after void inference.

| Validation | Result |
| --- | --- |
| `uv run --no-sync code-harness --all --format json` | 165 files; exit 0; zero errors and 47 warnings, exactly identical to the findings from an isolated HEAD baseline |
| `uv run --no-sync mypy src tests` | Passed; 164 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed; 165 files |
| `uv run --no-sync pytest -q` | 1,496 passed outside the sandbox |
| Focused generic, snapshot, semantic and suppression tests under branch coverage | 197 passed |

The sandboxed full suite encountered ACP subprocess timeouts and was interrupted.
The same isolated ACP test passed outside the sandbox; the complete suite then
passed outside it. Coverage 7.16.2 was installed into a temporary uv environment;
the repository dependency files were not changed.

Focused statement/branch evidence is retained in
`/tmp/code-harness-generic-final.coverage`. This measures the 197 focused tests,
not full-suite coverage:

| Module | Executed statements | Executed branch exits |
| --- | --- | --- |
| `semantics/results.py` | 54/56 | 16/18 |
| `languages/typescript/result_syntax.py` | 70/76 | 36/42 |
| `languages/python/result_syntax.py` | 88/102 | 38/52 |
| `languages/javascript/semantic_syntax.py` | 179/198 | 79/102 |

Uncovered paths include the shared recursion re-entry guards, unsupported or
missing annotation/body paths, several generic argument fallbacks, and existing
JavaScript import/assignment branches. These figures do not establish compiler
equivalence. Overload selection, class-level type parameters, arbitrary aliases,
generic callback contextual typing, Python keyword binding and generic parameter
environments remain bounded by the documented declaration fallback in
[checker configuration](checker-configuration.md).

## Inherited template methods (2026-10-15)

TypeScript and TSX now index abstract classes and abstract method signatures.
Language adapters select nominal bases without treating generic arguments as
additional ancestors. The shared index resolves lexical/imported declaration
identities, refreshes provisional bases after local bindings are established,
and resolves superclass calls and constructed/factory-result receivers.
Static methods retain separate declaration storage where the language has
separate namespaces; Python keeps its shared attribute namespace. Override method reads are
selected within the receiver's descendant hierarchy; parameter slots continue
to share reads across their resolved override contract. Dispatch memoization
belongs to one evidence computation, not a persistent source-name cache.

Ownership remains with the existing language adapters, semantic index, semantic
contracts and override analysis. No policy, limits, suppression mechanism or
dependency direction changed. `BindingSyntax` gains language-owned
`base_receiver`, `static_member` and `shared_member_namespace` interpretation;
`SemanticNodes` supplies defaults. No casts, broad payload carriers or workarounds were added.

`test_inheritance_usage.py` covers the exact template-method pattern in TS/TSX, concrete and
factory receivers, Python template methods, unrelated methods, unread override
families, replaced ancestors, siblings, local shadowing, generic arguments,
and static/instance identities. `test_inheritance_resolution.py` checks actual
declaration IDs and reads for imported abstract chains, Java abstract generic
owners and static methods, Python shadowed `super`, unresolved bases and Go
explicit composition. Exported-method exemptions cannot satisfy these evidence
assertions. Go composition is not treated as virtual inheritance.
`test_inheritance_snapshots.py` covers full, changed-definition and staged
analysis, unstaged base/body/override changes, read-only execution and fresh
evidence after staging a base change.

### Validation

| Check | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` | Exit 0; 168 files, zero errors, 56 discarded-result warnings |
| `uv run --no-sync mypy src tests` | Passed; 167 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed; 168 files |
| `uv run --no-sync pytest -q` | 1,558 passed outside the sandbox |
| Focused inheritance, semantic, constructor-property and generic-result regressions | 294 passed under branch coverage |

The sandboxed full suite encountered ACP subprocess failures and was interrupted.
All 34 ACP tests then passed outside the sandbox, followed by the full suite.
These are local checks, not CI results.

Coverage artifacts are `/tmp/inheritance-final.coverage` and
`/tmp/inheritance-final-coverage.xml`. The focused run executes 138 of 140 changed
executable statements; six changed branch sites remain partial. Changed
statements and partial branches were inspected. Uncovered defensive paths include a member expression
without receiver/name, superclass syntax outside any indexed class, and an
override read outside the supplied snapshot indexes. Other partial branches
include unsupported heritage clauses, duplicate inheritance edges, missing
candidate members and repeated ancestors. Coverage does not establish compiler
equivalence or whole-program runtime reachability.

The producer's previous 47 warnings remain. Nine additional warnings occur in
exception-path tests at `test_acp_review.py:71,78,85,96,102,189`,
`test_extensions.py:219,525` and `test_review_submissions.py:103`: constructed or
factory-produced receivers now resolve to methods with known return values.
Their deliberate exception assertions do not change the discarded-result rule.

Inference remains bounded: Python superclass lookup is not a complete C3 MRO
solver; dynamic mixins, arbitrary class aliases, overload selection, Go promoted
methods/interface dispatch, and whole-program receiver-flow specialization are
not established by these tests. The existing unresolved-member policy still
applies when evidence cannot resolve a receiver.
