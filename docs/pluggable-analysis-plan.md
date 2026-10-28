# Pluggable analysis and scoped exceptions

Status: Structural refactor implemented; scoped exceptions remain a draft proposal

The subsequent [language/rule decoupling design](language-rule-decoupling.md)
supersedes this historical proposal's language-owned rule composition, dual Python
parsing and parser-specific rule contexts. Its API 2 implementation and validation
are documented separately; the layout and contracts below are historical. The
scoped-exception proposal below remains separate and unimplemented.

This document records the original structural proposal for Code Harness. The
implemented class-based extension contracts and validation evidence are described
in [Plugin architecture](plugin-architecture.md). The coupling table and proposed
structure below describe the pre-refactor design, not the current implementation.
The exception proposal does not change the implementation or authorize a policy
exception. Module extraction, plugin registration, and exception support are
separate implementation phases. The later user-requested per-checker enable flags
and version 2 configuration are documented in
[Checker configuration](checker-configuration.md); they supersede the original
proposal's blanket prohibition on rule-disable controls. Scoped exceptions remain
unimplemented. The later syntax-warning behavior documented in those same
implementation guides supersedes this proposal's syntax-rejection requirements:
recovered-tree checks continue with an explicit accuracy warning, and Python AST
absence is represented in its language-specific context.

## Objectives

- Separate responsibilities and language-specific checks into cohesive modules.
- Add rules through explicit registration without changing engine dispatch.
- Preserve concrete types, canonical contracts, and domain-owned validation.
- Preserve existing diagnostics, parser failure behavior, and source snapshots.
- Support occasional reviewed exceptions without hiding the underlying findings.
- Keep gate execution read-only.
- Require Code Harness to check its own implementation and tests through the same
  public CLI, plugin registration, and policy evaluation used by other projects.

The current [engineering standards](engineering-standards.md) remain authoritative
until a policy amendment is reviewed and adopted. This proposal does not approve
individual suppressions, type erasure, or weakened architecture boundaries.

## Current coupling

| Current module | Responsibilities to separate |
| --- | --- |
| `rules.py` | Language dispatch, Go and TypeScript checks, suppression-comment detection |
| `syntax.py` | Grammar selection, traversal, shared syntax operations |
| `metrics.py` | Measurement, language-specific metric semantics, threshold enforcement |
| `architecture.py` | Ownership enforcement, import boundary enforcement, path matching |
| `models.py` | Source, configuration, architecture, diagnostic, and report contracts |
| `engine.py` | Concrete checker composition, execution, syntax rejection |

Python type checks and import extraction currently parse the same source
independently. Snapshot selection imports its path matcher from the architecture
checker. These are useful boundaries to resolve during the refactor.

## Proposed structure

```text
code_harness/
  source.py                 # Source, Language, source locations
  diagnostics.py            # Finding and rule identity
  policy/
    models.py               # Policy composition and validation
    paths.py                # Existing path-matching semantics
  parsing/
    treesitter.py           # Grammar selection and traversal
    python.py               # Python AST parsing
  analysis/
    contracts.py            # Narrow analyzer protocol
    engine.py               # Execution and failure ownership
  plugins/
    registry.py             # Registration validation
    builtins.py             # Concrete composition boundary
  rules/
    python/
      annotations.py
      signatures.py
      escapes.py
    go/
      types.py
    typescript/
      types.py
    comments.py             # Existing checker-suppression detection
  metrics/
    models.py               # Metrics and Limits
    measure.py              # Measurement and language semantics
    rules.py                # Threshold evaluation
  architecture/
    models.py               # Owner, Boundary, Import
    imports.py              # Extraction and normalization
    rules.py                # Ownership and dependency enforcement
  exceptions/
    models.py               # Scoped exception contracts
    evaluate.py             # Matching and validity checks
  reporting/
    models.py
    render.py
  snapshots.py
  cli.py
```

This tree is an ownership map, not a requirement to create every file immediately.
Keep small cohesive implementations together until their responsibilities justify
separation. Avoid delegation-only classes and one-file-per-rule fragmentation.

Each domain owns its contracts and validation. `Policy` composes those contracts
without becoming another catch-all model module. Move existing canonical types
rather than creating equivalent replacement models in several packages.

### Dependency boundaries

- Source and diagnostic contracts do not depend on implementations.
- Domain rule evaluation does not depend on CLI or snapshot infrastructure.
- Parsing owns concrete syntax representations and parser lifetimes.
- The engine depends on its narrow analyzer protocol, not concrete language ASTs.
- Concrete analyzers and checks meet at the plugin composition boundary.
- Exception evaluation consumes findings and validated exception policy; it does
  not control parser execution or individual checks.
- Reporting consumes evaluated results and does not decide exception eligibility.
- Snapshot selection uses policy path matching without importing a checker.

Update `.codeharness/code-harness.json` to reflect these responsibilities and dependency
directions. Audit nested package paths when changing its matching patterns. Policy
changes require a full audit and architecture review.

## Plugin contracts

Use two extension points:

| Extension | Responsibility |
| --- | --- |
| Language analyzer | Own parsing, language context, and compatible check execution |
| Rule bundle | Add checks over a declared, concretely typed analysis context |

The engine consumes a narrow analyzer protocol operating on `Source` and `Policy`
and returning findings. Concrete composition belongs in `plugins/builtins.py`.

Within an analyzer, Python checks receive a concrete Python context containing
`ast.Module`; tree-sitter checks receive their concrete tree context. Do not create
a universal context with optional AST fields or a dictionary of arbitrary
capabilities. Do not widen payloads and reconstruct their types inside plugins.

Parse once per required parser and share results within the owning analyzer.
Python may still require both tree-sitter and the Python AST for its existing
checks. Preserve both rejection paths and do not run dependent checks on invalid
syntax.

Registration must:

- Declare bundle identity, supported languages, API version, and emitted rule IDs.
- Reject duplicate registrations and conflicting rule ownership. A bundle may
  intentionally implement the same rule across several languages.
- Preserve existing rule IDs and deterministic diagnostic ordering.
- Fail when a required analyzer is missing or a plugin fails. A skipped required
  check must never become a successful result.
- Keep required syntax validation outside rule-disable and suppression controls.

Begin with explicit in-process registration. Adding a built-in bundle should
require implementation and registration without changing engine dispatch.
Separately installed plugin discovery is a later phase after the contract is
stable; its loading and compatibility boundary needs its own design before use.

## Scoped exception proposal

The recommended first mechanism is reviewed exceptions in policy configuration.
Inline directives are deferred. The existing policy prohibits suppression comments
and general bypasses, so exception support requires a separately reviewed policy
amendment.

Exception support does not itself authorize any exception. In particular, the
existing requirement for explicit case-specific user approval of type exceptions
continues to apply. An approval-reference field records evidence; its presence
alone does not prove authorization.

### Evaluation flow

```text
source -> parsing -> checks -> raw findings -> exception evaluation -> report
```

Checks always produce their findings. Exception evaluation changes a finding's
reported disposition while retaining the original diagnostic and the matching
exception identity. It must not remove checks from execution.

### Required exception information

| Field | Purpose |
| --- | --- |
| Unique exception ID | Stable audit identity |
| Exact rule ID | Prevent unrelated findings from being waived |
| Repository-relative path | Bound the affected file |
| Precise target | Identify a symbol or source anchor |
| Evidence fingerprint | Detect changes to the approved evidence |
| Rationale and accountable owner | Explain the need and responsibility |
| Approval reference | Link the case-specific review evidence |
| Expiry and removal conditions | Bound the exception's lifetime |
| Expected match count | Prevent accidental expansion |

Line numbers alone are insufficient identifiers because unrelated edits shift
them. Before implementation, specify fingerprint construction and source-anchor
resolution, including behavior when a symbol is renamed, moved, or ambiguous.
For metric exceptions, changed evidence must not silently authorize a larger
violation.

### Enforcement behavior

- Begin with explicitly eligible metric rules. Type and architecture exceptions
  require separate policy decisions.
- Never waive syntax, configuration, infrastructure, or plugin failures.
- Reject unknown rules, ambiguous matches, expired entries, and changed evidence.
- Detect unused entries during full audits. Changed-file audits must distinguish
  entries outside their scope from genuinely unused entries.
- Read exceptions from the same snapshot as source and policy. Unstaged exception
  edits must not weaken a staged audit.
- Preserve the existing requirement for full audit and review when staged policy
  changes are proposed.
- Show active and waived findings separately in text and JSON. Passing output with
  exceptions must show its exception count.
- Keep `type.suppression` detection separate from exception evaluation. Recognizing
  `# type: ignore` remains a check, not permission to waive another diagnostic.

Introduce exceptions through a new policy schema version. Existing version-1
policies retain their behavior. Define report schema compatibility before adding
exception dispositions to machine-readable output.

## Self-checking requirement

Code Harness must use its own gate as a required check on this repository. The
current [CI configuration](../.github/workflows/ci.yml) calls the
[engineering job](../.github/workflows/engineering.yml), which already runs
`uv run --no-sync code-harness --all`. The current
[repository policy](../.codeharness/code-harness.json) selects `src/*` and `tests/*`.
This wiring is the starting point to preserve and strengthen during the refactor;
its presence alone is not evidence of a successful CI run.

### Execution and scope

- Run the checkout's implementation through the public CLI after installing the
  locked development environment. Do not substitute a separately released checker
  for the code being changed.
- Require a full self-audit in CI on changes, including policy, registration, and
  checker changes. Changed-file checks may supplement this audit, not replace it.
- Check all authored supported-language source, tests, fixtures, and scripts.
  Extend the repository policy when those files appear outside `src/` and `tests/`.
  Literal invalid-code examples inside test strings remain test data; authored
  fixture files need an explicit scope decision under the engineering standards.
- Exercise the production analyzer registry and built-in bundles. There is no
  special self-check implementation or automatic exemption for checker code.
- Continue running mypy, Ruff, and pytest as independent required checks. A
  successful self-audit does not prove that the checker correctly detects faults.
- Preserve source, policy, and Git state during the audit.

### Architecture and exceptions

Replace the broad runtime owner with responsibilities matching the proposed
packages as they are introduced. Enforce concrete composition at the registration
boundary, implementation-independent source and diagnostic contracts, and the
separation of analysis from CLI and snapshot infrastructure. Keep policy paths
aligned with moved and newly added modules so enforcement cannot disappear during
extraction.

The checker must meet the same limits and type rules it applies to other projects.
Do not make self-checks pass by raising limits, excluding failing authored files,
disabling required bundles, or automatically creating exceptions. If exception
support is adopted, this repository uses the same reviewed, scoped, visible
mechanism as other projects; this requirement approves no individual exception.

### Evidence that self-checking works

Record a full self-audit baseline before structural extraction and repeat it at
each completed implementation phase. Report the inspected scope, finding counts,
and exit status. Existing failures remain visible until addressed; an unsuccessful
baseline must not be described as a pass.

Add behavioral tests through the public CLI using isolated repository fixtures.
Representative type, metric, and architecture violations must produce diagnostics
and a failing exit status; valid fixtures must pass. Missing required registration,
invalid policy, and plugin failures must fail closed. These fixtures verify the
enforcement path without introducing deliberate faults into the working tree.
Retain tests proving that gate execution leaves source and Git state unchanged.

## Implementation phases

### 1. Capture compatibility expectations

Record findings, messages, locations, ordering, CLI output, exit codes, and
snapshot behavior across representative existing fixtures. Existing tests provide
the starting behavior contract; supplement assertions where they currently check
only the set of rule IDs. Record the full repository self-audit baseline and its
current policy coverage.

### 2. Separate ownership

Split canonical contracts, move path matching, and centralize parsing without
changing enforcement. Preserve Go newline handling, Python AST rejection, nested
function metrics, import normalization, and suppression-comment detection.

### 3. Introduce registration

Route existing checks through typed analyzers and rule bundles. Verify required
language coverage, registration conflicts, deterministic ordering, and plugin
failure behavior. Preserve the default enabled checks and run the repository's
self-audit through this same registry.

### 4. Add reviewed exception support

After the policy decision, implement the versioned schema, eligibility, matching,
visible reporting, and snapshot semantics. Exercise expired, stale, ambiguous,
unused, out-of-scope, and overmatching exceptions through behavioral tests.

### 5. Audit and validate

Review canonical ownership, concrete types, dependency direction, and preservation
of read-only behavior. Run the required checks before completing gate changes:

```sh
uv run --no-sync code-harness --all
uv run --no-sync mypy src tests
uv run --no-sync ruff check src tests
uv run --no-sync ruff format --check src tests
uv run --no-sync pytest -q
```

Record requirement-to-test mapping and changed-line/branch coverage evidence as
required by the engineering standards. Keep structural extraction and exception
semantics independently reviewable.

## Acceptance criteria

- Adding a rule bundle requires no engine dispatch changes.
- Existing policies retain their diagnostics and failure behavior during the
  structural refactor.
- Concrete syntax and domain types remain intact through all extension points.
- Required check failures cannot become passes through missing registration or
  exception configuration.
- Exceptions remain bounded, reviewable, visible, and tied to inspected evidence.
- Staged, base, and full modes preserve their existing source-selection guarantees.
- Gate execution does not modify source, configuration, or Git state.
- The checkout passes its own full gate through the public CLI in required CI,
  with all authored supported-language files covered by the reviewed policy.
- New package boundaries are enforced on this repository, and representative
  failing fixtures demonstrate that the self-check execution path rejects faults.

## Decisions still open

- Whether configuration-only exceptions meet the suppression use cases, or inline
  directives need a later proposal.
- The initial eligible rule list and approval requirements for each rule family.
- Exact target-anchor and fingerprint semantics.
- Report schema compatibility and exception-validation error representation.
- Whether separately installed plugins are needed after explicit registration
  proves sufficient for built-in extensions.
