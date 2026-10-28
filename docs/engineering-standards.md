# Shared engineering standards

This policy applies to authored production code, tests, fixtures, adapters, scripts
and temporary helpers. This policy states the enforced rules and their limits;
supported options are recorded in [Checker configuration](checker-configuration.md).

## Ownership and architecture

1. Give every file a named domain, application, infrastructure or presentation
   responsibility. Keep stage-specific contracts, interpretation and validation
   inside their stage. Avoid catch-all `utils`, `common` and `helpers` ownership.
2. Shared scheduling and lifecycle infrastructure knows only its narrow protocol.
   It must not import concrete stage payloads, even through type-only imports.
   Compose concrete implementations at a registration/composition boundary.
3. One component owns each mutable state, transaction, resource lifetime and
   terminal failure. Preserve cancellation, cleanup, ordering and exactly-once
   completion through refactors. Keep domain rules independent of adapters.
4. Use composition, cohesive objects and narrow interfaces. An abstraction must
   own policy, an invariant, a real boundary or a resource lifetime. Small pure
   functions are welcome. Avoid delegation-only hierarchies and callback bags
   that obscure domain ownership.
5. Implement language adapters and rules as independently registered classes with
   narrow typed interfaces. Language objects own identity, suffixes, tree-sitter
   grammar and syntax interpretation. Application composition owns enabled and
   required rules and connects them to compatible language capabilities. All
   language parsers produce the same concrete tree-sitter context; shared rules
   consume typed capabilities without selecting language identities or importing
   language implementations. Keep exceptional grammar and language-specific
   checks with the language owner. Shared engines and discovery use registration;
   do not dispatch on language or rule identities with conditionals or callback
   bags. Rule objects own their behavior; forwarding wrappers around procedural
   dispatch do not establish ownership. Configure
   `checkers["architecture.object_model"].paths` for extension implementation paths.
   The [decoupling design](language-rule-decoupling.md) defines the target and
   migration obligations; [Plugin architecture](plugin-architecture.md) records
   the current API 2 runtime and its compatibility changes.
6. Export only consumed supported APIs. Test public behavior through concrete
   seams. Do not expose internals or clone domain models merely to simplify tests.
7. Search existing types before introducing a DTO, payload or fixture wrapper.
   Keep one canonical type per contract. A second type needs distinct domain
   meaning, external schema or lifecycle invariants and a tested transition.


8. Organize source around the feature or domain that owns its behavior. Keep
   feature-specific rules, validation and supporting contracts with that owner;
   a technical label such as `rules`, `helpers` or `models` does not by itself
   justify moving them to the package root or a shared directory. Promote code
   to a shared owner only when it has a real shared responsibility and concrete
   consumers. For example, Python-only type rules belong under `languages/`
   alongside the Python plugin; shared analysis engines depend on their typed
   interfaces. Enforce declared placement conventions with
   `checkers["architecture.structure"].placements`. Review placement together with
   imports and canonical ownership; path checks cannot infer domain meaning.

For language analysis, retain the original tree-sitter tree and source locations.
Extract only the typed facts needed by consumers; reuse canonical contracts.
Do not build a generic dictionary AST, a second universal AST or a capability bag
requiring casts. Grammar adapters interpret syntax; shared analysis owns resolution
and reusable evidence; rules apply policy. An analysis session owns each exact
snapshot's parse lifetime and mutable resolution state. Required unsupported
capabilities fail registration; optional unavailable analysis is explicitly
reported. Rule identity ownership is unique within each composed execution.

The repository import policy prohibits runtime Python AST dependencies and
language-owned analyzer composition. The implementation follows the approved
decoupling design; its dated validation evidence records the checked scope and
remaining inference limits. Policy enforcement does not authorize suppressions.

## Types and boundaries

Preserve known concrete types end to end. Do not widen to `Any`, `object`, `any`,
`unknown`, `interface{}`, generic JSON trees, broad base classes, bare collections,
unconstrained generics or unrelated unions and later reconstruct the original.
Use discriminated domain alternatives and typed keys/elements. Narrow untrusted
input once, at actual ingress, into a declared contract; encode at actual egress.
Do not carry structured application payloads internally as JSON strings or bytes.

Do not use casts, non-null/double assertions, type suppressions, unchecked model
construction, permissive schemas, reflection bags, serialization round trips or
broad mocks to bypass this rule. The third-party boundary exception below permits
only the erasure needed by that boundary.
Legitimate syntax trees retain a real syntax-domain contract. Literal test source
snippets are source inputs, not serialized application payload carriers.

JSON encoding uses shared alias and output-flow analysis with language-owned
serializer/API recognition. Python JSON encoding is permitted at proven output destinations: unshadowed
`print`, imported `sys.stdout`/`sys.stderr` writes, `pathlib.Path.write_text`, and
text writes to a writable `open` context. A single-assignment local may forward
the encoding only when every observed use reaches permitted output. Memory
buffers, arbitrary write-like method names, internal consumers and decoding the
encoding back into application data do not establish egress. Other output APIs
need actual configured library evidence, reviewed `type.broad.encoding.outputs`
payload declarations, source/class/member-scoped `instance_outputs` approvals,
or an explicit language adapter. Encoder/decoder declarations
under `type.broad.encoding` extend recognition and retain round-trip rejection.
JavaScript/TypeScript/TSX apply the same policy to native `JSON.stringify`, with
recognized console, standard-stream and imported filesystem outputs. Go recognizes
imported JSON Marshal/MarshalIndent results with explicit byte/error separation;
Java recognizes selected imported Gson/Jackson serializer signatures. Scoped
instance outputs use language-owned receiver proof across all supported languages.
See [encoding configuration](checker-configuration.md#configuring-encoding-apis)
for exact signatures, output slots and conservative inference limits.

At an actual call into third-party code, a type-erased dictionary is permitted
as a library input, including keyword arguments. Keep the application's contract
concrete until that outbound boundary. Convert values returned by the library
into declared typed objects at ingress before carrying them through application
code. A forwarding parameter may use the library dictionary contract when every use
goes directly to that library. This exception does not permit erased internal
storage, application return types or general transport between components.

Callbacks reverse the direction: callback parameters are outputs of third-party
code and must be narrowed into typed objects at callback ingress; the callback's
return value is input to the library and may use the erased dictionary required
by its contract. Establish the actual third-party call or callback registration;
a parameter name such as `kwargs`, an import alone, or a boundary-like function
name is not sufficient evidence. Casts and unchecked reconstruction do not count
as conversion or validation.

TypeScript `as const` and checked `satisfies` preserve useful contracts and are
allowed. Go capability interfaces must declare the operations their consumers
need. JavaScript public contracts need concrete JSDoc or a typed boundary with
type-aware checking. Other exceptions require explicit case-specific user approval,
an exact path/symbol, rationale, validation and removal conditions. The gate
supports explicit per-checker `enabled` flags in project policy; these
are reviewable policy decisions and do not authorize type erasure or create an
blanket boundary exemption. Source suppression directives remain prohibited except
for explicitly approved next-line diagnostic exceptions available in every supported
language, described in [comment suppressions](comment-suppressions.md).

Required facts must not default to guessed values, success, an arbitrary first
entry or an empty payload. Model absence, rejection and unresolved evidence
explicitly. Shape validation does not prove authorization, freshness or business
acceptance; preserve those checks at their actual use points.

## Guarded field projections

Review repeated conditional field copies as a contract and mapping responsibility
in every supported language. Three distinct guarded destination fields in one
consecutive local region trigger `structure.guarded_projection`, independently
of function complexity. A candidate copies the tested source field or a primitive
literal established by equality, with an absent/empty other branch. Conditional
object/dictionary spreads have the same policy where the language supports them.

Keep source receiver and destination construction identities distinct. Do not
merge across unrelated statements, properties, calls, reassignments, nested
functions or control-flow regions. Dynamic keys, transforms, business operations,
validation and unproved predicates do not establish this pattern. Findings retain
locations and predicate distinctions; no autofix is safe by default.

Remediation must preserve concrete field associations and omission semantics.
Do not replace guards mechanically with spreads, casts, erased dictionaries,
serialization filtering or forwarding helpers, and do not weaken optional-field
types just to pass the gate. See [Guarded field projections](guarded-projection.md)
for exact adapter coverage, conservative inference limits and validation evidence.

## Unused declarations and results

Report unused parameters, functions and class fields. A field must have a read
usage: declaration, initialization and subsequent writes alone do not make it
used. Associate reads with the actual declaring type and instance; a same-named
field on another class is not evidence. Account for callers, closures, inherited
contracts, registered callbacks and framework entry points before declaring a
function unused. For methods in a resolved inheritance contract, count a
parameter as used when its corresponding slot is read by any implementation in
that override family. A parameter unread throughout the family, or an isolated
callback parameter with no read evidence, remains reportable. Explain required
signature constraints rather than deleting the parameter.

When an object is passed into third-party code, all of that object's fields may
be treated as used by the library. Apply this exemption to the actual object
passed, including an object returned by a registered callback, and do not infer
it for unrelated objects or for values arriving from the library.

Warn when a non-void return value is discarded. Such warnings do not fail the
gate. A call made solely for side effects can still discard a meaningful result;
absence of return-type evidence is not proof that the call returns a value.
Record the checked scope and unresolved external usage instead of claiming a
repository-wide unused declaration from an isolated source snapshot.

## Readable implementation

Use meaningful names, one operation and abstraction level per function, minimum
visibility and the language's standard formatter. Prefer named domain operations.
Callbacks belong to the component that owns their behavior. Do not compress code
or split resource/transaction ownership merely to satisfy a metric.

Default maxima: **50 substantive physical lines, 50 statements, complexity 10,
control nesting 3, five parameters**. Count function signatures and nested bodies
in line spans. Blank/comment lines and Python docstrings are excluded. Nested
functions receive independent control-flow checks; their decisions do not inflate
the enclosing function's complexity. Go grouped parameter names count separately;
Go receivers and Python `self`/`cls` do not consume the argument budget.

Document purpose, public contracts, invariants and failure behavior. Use Python
docstrings, public API documentation and durable architecture records. This shared
policy does not require or ban ordinary rationale comments. Follow the owning
project's explicit comment policy. Checker-suppression comments are prohibited
except for the explicitly approved next-line mechanism available in every
supported language.
Reasons record human approval; the checker does not prove the exception is safe.
Do not delete existing rationale or code without authorization.

Use operational logs that explain event, operation, outcome and next action with
appropriate levels, stable identifiers, bounded values and one terminal-error
owner. Normalize control characters and redact secrets. Use lazy Python logging.
Approvals granted in other projects do not transfer here.

## Automated gate

| Rule | Mechanical evidence |
| --- | --- |
| `size.lines` / `size.statements` | Function token-bearing line span / statement count |
| `size.complexity` / `size.nesting` | Decisions and nested control nodes |
| `size.parameters` | Explicit parameter count including grouped Go names |
| `structure.guarded_projection` | Distinct guarded field projections in consecutive local statement/literal regions across all supported languages |
| `type.annotation` | Recognized broad/bare Python annotations and forward annotations |
| `type.signature` | Missing Python parameter/return annotations |
| `type.broad` | Recognized Python typing markers and internal `json.dumps` erasure, JS/TS `JSON.stringify` erasure, recognized Go/Java serializer erasure, TS broad/empty types, Go empty interfaces/`any`, Java `Object`, unbounded wildcards and recognized raw collections |
| `type.boundary` | Recognized third-party outputs used without typed ingress conversion |
| `unused.parameter` | Declared parameters without resolved read usage |
| `unused.function` | Non-exported functions and methods without resolved references |
| `unused.field` | Fields without reads; initialization and writes do not count |
| `unused.return` | Warning for a known non-void result discarded at a call site |
| `type.assertion` | Python typing casts, TS assertions except `as const`, TS non-null assertions, Java reference casts |
| `type.suppression` | Recognized suppression comments and Python no-type-check markers |
| `imports.wildcard` | Python wildcard imports |
| `architecture.owner` | Missing or overlapping configured file owners |
| `architecture.structure` | Selected source modules outside their configured owning locations |
| `architecture.import` | Literal/normalized dependencies forbidden by project policy |
| `architecture.dispatch` | Recognized language/rule identity comparisons and match/switch dispatch |
| `architecture.object_model` | Non-underscore module functions in configured `architecture.object_model.paths` extension paths |

Complexity starts at one and increments for recognized branches, loops, catches,
non-default cases, conditional expressions, comprehension decisions and short
circuit operators. Control nesting measures nested recognized control constructs;
Python `elif` alternatives share their parent's depth.
These are syntax metrics, not compiler CFG metrics; case/exception semantics differ
between languages. Formatting/line length remain language-tool checks.

Third-party classification uses exact import specifiers in `third_party_modules`.
See [Checker configuration](checker-configuration.md#third-party-boundaries-and-usage)
for directional examples and semantic resolution limits.

The parser-backed gate is read-only. Checker options are grouped by responsibility;
`function_size` owns all five function metrics. Other checker keys match their
diagnostic IDs. Only `include` and `exclude` control global file selection.
Every checker defaults to enabled; omit default-only entries and `enabled: true`.
Reports disclose disabled checker names while findings retain their diagnostic IDs.
Malformed configuration and tool failures fail closed. Syntax rejection emits a
warning on stderr and permits best-effort checks on the recovered tree. Results
may be inaccurate; analyses requiring complete syntax must disclose or qualify
unavailable evidence. Python type and import checks use the same recovered tree. Syntax warnings are not defects or configurable checkers and
do not change the exit status. Parsing is skipped if all analyzer rules are disabled.
Changed modes analyze complete snapshots but report affected definitions and
module statements. Function edits include signatures, decorators and bodies;
class-header edits select the class. Deletion anchors participate in expansion.
Ownership and placement still apply to every changed file. Reports disclose this
scope; full audits expose historical debt. Configuration changes require architecture review;
neither excluding debt nor increasing limits is remediation.

## Semantic review and delivery evidence

The gate cannot prove inferred library types, meaningful unions, generic type
relationships, arbitrary alias chains, canonical model ownership, permissive schemas,
all serialization boundaries, honest validators, authorization, all dead code, lifecycle
safety or logging quality. Review these through the changed call chain, including
tests and third-party interfaces. Dynamic imports, escaped module strings, build
aliases and compiler resolution need language-aware dependency checks or review.

Map requirements and risks to observable assertions. Cover relevant invalid,
empty, boundary, retry, cancellation, cleanup and failure cases. Measure statement
and branch coverage; inspect missing changed lines and partial branches. Preserve
behavioral assertions, fixture ownership and exact test discovery. A percentage
alone does not establish adequate tests. Coverage is a separate delivery gate,
not implemented by this syntax tool.

Before accepting a change, record:

- Owners, dependency direction, canonical contracts and any approved exceptions.
- Exact formatter/linter/type-checker, architecture and test commands and results.
- Requirement/risk-to-test mapping and changed-line/branch coverage evidence.
- Known historical debt and unresolved semantic or inference gaps.

Never automatically roll back, revert, discard, reset, restore, overwrite or
delete existing changes to satisfy a gate. Preserve the state and obtain explicit
authority if reversal is necessary. Hooks must not stash or auto-fix. Project
publication status and compatibility requirements must be decided explicitly.
