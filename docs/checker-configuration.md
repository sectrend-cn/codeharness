# Checker configuration

`.codeharness/code-harness.json` is the policy used when checking a target repository. It does
not modify application behavior or rewrite source. Error findings return exit code 1; warning-only results return 0;
invalid configuration and analysis failures return exit code 2.

Each repository commits its own policy at this default path. Start with
[the example](../examples/.codeharness/code-harness.json) and adapt it to the
repository's architecture. All selection and checker paths are relative to the
repository root, not `.codeharness/`.

The bundled agent skill repeats these facts per checker under
[the checker index](../.agents/skills/code-harness/references/checkers.md), one
page per checker in `references/checkers/`; change both carriers in the same batch.

`--config` selects the policy path; it stays relative to `--root` in every mode and
must name a path inside the root. There is no automatic fallback to a root-level
policy file. Staged checks read that exact path from the index and reject staged
policy changes pending a full audit and review.

Checker settings belong under `checkers`; top-level checker settings are rejected.

The policy separates global file selection from checker options:

```json
{
  "version": 2,
  "include": ["src/*", "tests/*"],
  "exclude": [],
  "checkers": {
    "function_size": {"lines": 50},
    "architecture.object_model": {
      "enabled": false,
      "paths": ["src/plugins/*"]
    }
  }
}
```

This example checks supported source files under `src/` and `tests/`, enforces a
50-line function limit, and disables non-underscore module-function checking. Other
checkers retain their defaults, including language/rule dispatch checking.

## Options by checker

Every checker supports a strict boolean `enabled`, defaulting to `true`. Omission
of a checker or an option preserves its default. Flags such as `"false"` or `0`
are errors. Unknown checker IDs and options are errors, including when a checker
is disabled. Each entry configures one logical checker. Function-size diagnostics
share one checker; other checker names match their diagnostic IDs. There is no
need to write `enabled: true` or entries that contain only default options.

| Checker ID | Additional options and defaults | What it checks |
| --- | --- | --- |
| `structure.guarded_projection` | `min_fields: 3` (integer, at least 2) | Repeated guarded field copies in every supported language |
| `function_size` | `lines: 50`, `statements: 50`, `complexity: 10`, `nesting: 3`, `parameters: 5` | All five function metrics |
| `type.annotation` | None | Broad or bare Python annotations |
| `type.signature` | None | Missing Python parameter/return annotations |
| `type.broad` | `encoding: {encoders: [], decoders: [], outputs: [], instance_outputs: []}` | Recognized broad type markers and JSON encoding outside proven output or permitted third-party inputs |
| `type.boundary` | None | Unconverted recognized third-party results and callback inputs |
| `unused.parameter` | None | Parameters without read usage |
| `unused.function` | None | Non-exported functions and methods without references |
| `unused.field` | None | Fields without reads, including write-only fields |
| `unused.return` | None | Non-failing warnings for discarded known return values |
| `type.assertion` | None | Unchecked type assertions and casts |
| `type.suppression` | None | Shared foreign suppression directives in every supported language, `NOSONAR`/`CHECKSTYLE:OFF`/`noinspection` only in Java, plus malformed or unused [next-line exceptions](comment-suppressions.md) |
| `imports.wildcard` | None | Python wildcard imports |
| `architecture.owner` | `owners: []` | Exactly one responsibility owner when owners are configured |
| `architecture.structure` | `placements: []` | Selected source paths must match their configured owning locations |
| `architecture.import` | `boundaries: []` | Forbidden source-to-import dependencies |
| `architecture.dispatch` | None | Recognized language/rule identity dispatch |
| `architecture.object_model` | `paths: []` | Non-underscore module-level functions in matching extension files |

Metric maxima must be positive integers and are inclusive. Owners contain `name`
and `paths`. Boundaries contain `name`, `sources`, and `forbidden_imports`.
Ownership does not infer dependency permissions. All matching boundaries apply.
An empty owner list, boundary list, or object-model path list provides no
project-specific facts for that check to enforce.

`include` and `exclude` are global and cannot be placed inside a checker. They use
case-sensitive shell matching of root-relative paths, with `*` spanning `/`.
Architecture-specific paths select where that one architecture check applies;
they do not remove files from other checkers.

The schema covers 18 logical checkers, which produce 22 built-in diagnostic IDs.
Language syntax, region boundaries and a configuration example are documented in
[the guarded projection checker reference](../.agents/skills/code-harness/references/checkers/structure.guarded_projection.md).
Custom plugin settings continue
to belong to their typed plugin constructors; arbitrary custom checker names in
this JSON are rejected.

## Language coverage

Six built-in analyzers cover seven languages: Python (`.py`, `.pyi`), Go
(`.go`), Java (`.java`), JavaScript and JSX (`.js`, `.jsx`, `.mjs`, `.cjs`),
TypeScript (`.ts`, `.mts`, `.cts`) and TSX (`.tsx`). Every checker is enabled by
default for each selected file. `enabled: false` disables that checker for every
selected file: there is no `enabled` option scoped to one language or one file,
and `include` / `exclude` drop files from all checkers at once. Architecture
`placements`, `boundaries` and `paths` select where that one architecture check
applies rather than enabling or disabling it. `owners` is not a scope selector:
when it is configured and the checker is enabled, every selected file must match
exactly one owner. Both are described in [Options by checker](#options-by-checker).
Coverage differences therefore come only from the diagnostics an analyzer registers.

Java analysis uses the locked `tree-sitter-java` grammar and needs no JDK or build
step.

Every analyzer registers the same base set of 17 diagnostic IDs:

- Usage: `unused.parameter`, `unused.function`, `unused.field` and
  `unused.return`, which is always a warning and never fails the gate.
- Boundaries and directives: `type.boundary` and `type.suppression`.
- Function metrics: `size.lines`, `size.statements`, `size.complexity`,
  `size.nesting` and `size.parameters`, all configured through the single
  `function_size` checker.
- Architecture: `architecture.owner`, `architecture.structure`,
  `architecture.import`, `architecture.dispatch` and
  `architecture.object_model`.
- Structure: `structure.guarded_projection`.

The remaining five diagnostic IDs are registered per language:

| Analyzer | Additional diagnostic IDs |
| --- | --- |
| Python | `type.annotation`, `type.signature`, `type.assertion`, `type.broad`, `imports.wildcard` |
| Go | `type.broad` |
| Java | `type.assertion`, `type.broad` |
| JavaScript and JSX | `type.broad` |
| TypeScript and TSX | `type.assertion`, `type.broad` |

A registered diagnostic can only report for the analyzer that registered it:
`type.annotation`, `type.signature` and `imports.wildcard` appear in Python files
only, and `type.assertion` covers Python, Java, TypeScript and TSX but not Go or
JavaScript.

`type.broad` recognizes different markers in each language, in addition to the
JSON encoding forms described in
[Configuring encoding APIs](#configuring-encoding-apis):

| Language | `type.broad` markers |
| --- | --- |
| Python | `typing.Any`, `typing_extensions.Any` and `pydantic.JsonValue` references, plus internal `json.dumps` results |
| Go | `any` and empty interfaces, plus imported `encoding/json` `Marshal`/`MarshalIndent` results |
| Java | `java.lang.Object`, unbounded wildcards and recognized raw collections, plus recognized Gson/Jackson results |
| JavaScript and JSX | `JSON.stringify` results only; JavaScript has no type annotations to check |
| TypeScript and TSX | `any`, `unknown`, `object` and empty object types, plus `JSON.stringify` results |

Python broad annotation markers such as `Any` or `object` are reported by
`type.annotation`, and a `typing.Any` reference additionally triggers
`type.broad`, so one annotation can produce a finding from each checker.
Coverage of a diagnostic does not promise complete evidence for every construct:
resolution limits are described in
[Third-party boundaries and usage](#third-party-boundaries-and-usage) and
[Configuring encoding APIs](#configuring-encoding-apis).

## Disabling and shared execution

Set `enabled: false` to disable one checker across selected files. Text reports
list disabled checker names, and JSON reports include a `disabled_checkers` array.
For example, `"function_size": {"enabled": false}` disables all five function
metrics and is reported as `function_size`. Findings still use `size.lines`,
`size.statements`, `size.complexity`, `size.nesting`, and `size.parameters`.
The same source may still violate a different enabled checker. For example,
Python `typing.Any` can trigger both `type.annotation` and `type.broad`.

Fully disabled rule bundles are skipped. A bundle with enabled diagnostics may
still share traversal work across its checks; disabled diagnostics are filtered
individually. Errors and undeclared output from an executing bundle still fail
analysis. Disabling a checker does not permit broken plugin registration.

Parsing constructs the context used by enabled checks. Invalid syntax emits
warnings on stderr, including when `--format json` is selected, and checks
continue on the recovered tree. Parser warnings are recorded apart from findings
and never change defect counts or the exit status; they disclose that results may
be inaccurate. Every language uses a tree-sitter context. Rules consume the
available recovered syntax, while analyses requiring complete evidence may be
unavailable. For Java, recovered syntax produces warnings and still permits syntax
checks, while usage and boundary diagnostics require a complete parse. Parser
infrastructure and semantic preparation failures return exit 2. When every
diagnostic provided by an analyzer is disabled, parsing and bundle execution are
skipped.

`syntax.invalid` has been removed from the checker schema and rule declarations.
Remove any `checkers["syntax.invalid"]` entry from existing policies; it is now
rejected as an unknown checker. Parser warnings have no enable/disable option.

The repository's own policy keeps every checker enabled and retains the existing
thresholds, ownership assignments, dependency boundaries, and extension paths.
Changing enable flags is a policy change subject to the same full-audit and review
requirements as changing thresholds or boundaries. Staged-policy changes remain
blocked by the staged gate; unstaged options do not alter index-based checks.

## Third-party boundaries and usage

Declare third-party import specifiers explicitly at policy level:

```json
{
  "third_party_modules": ["vendor.client", "@vendor/sdk", "example.com/vendor/sdk"],
  "checkers": {}
}
```

The default is an empty list. Entries match the actual import module exactly;
import aliases retain that identity. Do not list application modules to bypass
typing. This setting grants a directional boundary exception, not a file or
checker exemption. Internal dictionaries and other broad carriers remain checked.
Disabling `type.boundary` disables its diagnostics but does not alter third-party
classification used by the other type and field checks.

A dictionary, or a directly forwarded dictionary parameter, can erase value
types when every read supplies an argument to a configured library. Python
`**kwargs`, Go maps and TypeScript `Record` annotations are recognized. Type
assertions and suppression directives remain errors. JavaScript receives the
same usage and boundary analysis; it still needs a separate type-aware checker.

For a callback registered as a library argument, its return dictionary is library
input. Its incoming dictionary parameters must be converted at callback ingress.
The check recognizes declared constructors, concrete-return conversion functions
and Python scalar conversions, including extraction of dictionary entries.
A callback also called by application code does not gain a broad return contract.
Library results cannot be returned or passed through application code raw. Values
already constructed with a concrete generic library contract, and explicit `new`
expressions, retain that contract. Type-only schema metadata and fields materialized
by a configured external metaclass are not raw application result carriers.
Mechanical recognition of a conversion does not prove its validator is honest.

In Python, decorator factories supply declaration behavior rather than application
payloads, while ordinary third-party payload results still require ingress
conversion. This does not add a general payload exemption for decorators'
arguments.

Objects passed to configured libraries, including callback return objects, have
all their declared fields treated as consumed. Configured external base classes
also consume their class objects through metaclass construction. This repository
lists `pydantic` for its externally materialized model fields. Field reads resolve
through concrete receivers, annotations, constructors, imports and known bases;
a write, initialization or deletion alone is not a read.

Usage analysis runs automatically for Python, Go, Java, JavaScript/JSX and TypeScript/TSX.
It resolves lexical scopes, closures, literal imports and Go files in the same
package. Public Python module APIs, exported Go/JS/TS functions, non-private,
annotated or overloaded Java methods, recognized runtime entry points and
declaration-only signatures retain their external-use contracts.
Methods linked by resolved inheritance share parameter-use evidence. A read in
any implementation makes the corresponding parameter used throughout its
override family, including base and sibling implementations. Positional arguments
match by position, keyword-only arguments by name, and variadic slots separately.
Extra arguments and parameters unread throughout the family remain findings;
unrelated same-named methods and constructors do not gain this exemption. This
also applies to imported bases and JS/TS `extends` clauses. Structural interface
relationships without resolved inheritance still require review. Python
`self`/`cls`, JS `this`, and blank `_` bindings are not unused-parameter candidates.
TypeScript constructor parameters marked `public`, `protected`, `private` or
`readonly` can declare instance properties, and `unused.parameter` accepts
resolved reads of those properties as usage of the exact constructor parameter
declaration. Initialization and writes alone remain insufficient, and ordinary
parameters or unrelated declarations with the same name remain reportable.

`--all` links all selected snapshots. Changed audits read unchanged reference
files from the same view: working files for `--base`, index blobs for `--staged`.
Only the originally selected files receive findings; JSON `files` retains that
scope and `usage_files` discloses the reference scope. These reads do not modify
source or the index. In-process callers can use `AnalyzerRegistry.analyze_sources`
with the built-in registry to obtain the same cross-file resolution; `engine.check`
checks one snapshot. Custom registries can register a `SemanticParser` explicitly.

Every finding now includes `severity`, defaulting to `error`. `unused.return` is
always a `warning`; text labels it and JSON retains it in `findings`. A known
non-void local or resolved imported function result discarded as a standalone
call, Python/Go `_` assignment, or JS `void` expression produces a warning.
Unknown external return types are not guessed. Warnings alone leave exit status 0.

Result classification uses the call expression as well as the declaration.
TypeScript/TSX direct generic results such as `run<R>(work: () => R): R`
substitute explicit type arguments or infer the result from resolved callbacks.
Python supports the corresponding imported `Callable[..., R]` contract with a
PEP 695 parameter or an imported `typing.TypeVar` declaration. JavaScript supports
direct forwarding of an unchanged callback parameter. A callback's declared
contract takes precedence over its body; an unannotated callback with no value
returns supplies no-result evidence. Expression bodies can call resolved local
or imported functions. Each invocation is classified independently.

Promises, coroutines, generators and containers remain value results, even when
their payload is `void` or `None`. Java `Void` and Go empty structs also remain
values; these languages cannot substitute a no-result type for a generic value
parameter. Their existing declaration and overload fallback remains unchanged.

Inference distinguishes no-result, value-result and unresolved evidence.
Unresolved cases retain the declaration-based warning behavior. It does not
implement compiler overload selection, arbitrary type aliases, class-level
generic substitution, generic callback contextual typing or general dataflow.
Overloaded TypeScript callbacks, reassigned callbacks, destructured/rest
parameters, unsupported wrappers and unresolved external callbacks do not prove
`void`. Python keyword argument binding and generic relationships outside direct
callback results retain the fallback. Nested generic calls inside a resolved
callback expression are supported; forwarding through generic parameter
environments is not. There is no compiler runtime dependency.

Cross-file inference reads declarations and callbacks from the same selected
snapshot view as usage resolution. No result is cached on a declaration or across
analysis sessions; staged checks use index content even when worktree signatures
or callback bodies differ. Exact-line suppression is applied after inference,
so a suppression targeting a now-proven void call becomes stale.

These are bounded semantic checks, not compiler or whole-program proofs. Dynamic
imports, arbitrary aliases, reflection, dynamic attributes, complex generic flow,
framework registration and external consumers may require review. An unresolved
member read or protocol dispatch defers same-named member candidates instead of
asserting they are unused. Exported APIs are not automatically declared dead.
Import resolution uses the available policy-selected snapshots; package/build
alias resolution is not a replacement for language tooling. Review remaining
candidates before changing code. The gate never removes or rewrites unused code.

Java evidence is syntax-backed rather than javac type checking. Overload selection,
generic substitution, reflection, annotation processing, generated accessors,
wildcard/static-member project linking, fully qualified expression resolution and
external classpaths are not resolved at compiler level. Nested or anonymous class
ownership, generated members and unresolved external references retain the shared
engine's inference limits.

## Python JSON encoding

`type.broad` also reports calls to Python's `json.dumps` that replace concrete
internal values with JSON text. It recognizes module imports, renamed imports
and `from json import dumps`, plus single-assignment callable/module aliases such
as `encode = json.dumps` or `codec = json`. Alias chains and local shadowing use
the existing semantic index. Strings containing source examples and unrelated methods named
`dumps` are not encoding calls. Other serializers can be registered in the
encoding API configuration below.

The existing `third_party_modules` policy remains directional. A JSON encoding
is permitted when supplied directly to a configured library, including keyword
arguments, inline container values and returns from callbacks used exclusively
by that library. A local binding is permitted only when it has one assignment
and every resolved read leads to a permitted library input or proven output. Internal consumers,
retained fields, ordinary helper returns and reassigned carriers remain findings.
An internal transformation between encoding and the library call does not receive
an exemption. Dictionary keys are not treated as outbound payload values.

For example, with `vendor` in `third_party_modules`:

```python
import json
import vendor

vendor.send(body=json.dumps({"count": 1}))
```

is permitted. An internal `return json.dumps(payload)` is reported. A value sent
to `vendor` and also consumed by application code is reported at its encoding.
A `json.loads(json.dumps(payload))` round trip remains an error even if `json`
is listed as a third-party module. This also covers stable aliases of the decoder
and single-assignment carriers passed into it. Merely configuring the encoder's
module does not exempt its output from this rule.

Actual serialization output is permitted independently of third-party policy:

- Unshadowed `print`/`builtins.print` to the terminal.
- Imported `sys.stdout.write` and `sys.stderr.write`.
- `write_text` on a recognized `pathlib.Path` construction or stable local alias.
- `write` on an enclosing writable text `open`, `builtins.open` or `io.open`
  context binding, and `print(..., file=...)` to that file or a standard stream.

`print(json.dumps(payload))` is therefore allowed. A local JSON string may be
forwarded to these outputs only when every resolved read reaches permitted output.
`StringIO` writes, unknown or shadowed destinations, reassigned carriers, and
arbitrary methods named `write` or `send` remain insufficient evidence. This
output exception belongs to JSON encoding; it does not exempt broad annotations
or casts passed to `print`.

JSON encoding shares the existing broad-type checker and its
`checkers["type.broad"].enabled` setting, which defaults to enabled. Disabling
`type.boundary` does not change the
third-party evidence used by this check or permit internal JSON encoding.
Python JSON checks consume the shared tree and boundary evidence, including
available syntax after tree-sitter recovery; there is no second AST rejection path.
Reassigned or dynamically selected callables, monkey-patched imports, unresolved
library receivers, and arbitrary cross-function data flow remain review limits.
Stable single-assignment aliases are supported; this is not control-flow-sensitive
alias analysis. Other serializers and unrecognized output APIs remain outside
this JSON check's coverage.

## Source structure

`architecture.structure` enforces declared source-placement conventions. A file
matching a placement's `paths` must also match at least one of its
`allowed_paths`. Each matching placement is enforced independently; an unrelated
placement does not affect the file. Patterns use the existing case-sensitive
shell matching, where `*` can span directory separators. Paths are repository
relative and pass through the same global include/exclude selection as other
checks. The checker defaults to enabled with an empty `placements` list.

For example, this repository requires language rule modules — `*_rules.py`
modules and each language's `rules.py` — to live with the language plugins:

```json
"architecture.structure": {
  "placements": [{
    "name": "language rule modules belong with language plugins",
    "paths": ["src/code_harness/*_rules.py", "src/code_harness/languages/*/rules.py"],
    "allowed_paths": ["src/code_harness/languages/*"]
  }]
}
```

`src/code_harness/python_rules.py` fails this constraint even if another policy
assigns it a valid owner. `src/code_harness/languages/python/rules.py` passes:
the `src/code_harness/languages/*/rules.py` pattern covers that path. Application
composition in `plugins/builtins.py` imports `PythonTypeRule` from this module:
the language owner covers that path, and existing dependency restrictions and
object-model checks apply to it.

Placement, ownership and import restrictions have independent enable flags.
Placement diagnostics report the source path at line 1, name the constraint and
list the allowed locations. All built-in languages use the same structural
check. Changed modes apply it only to selected source files; staged checks use
index paths and index policy, including when the working tree has moved a file.
The gate never moves files itself.

This is explicit convention enforcement. It does not infer a file's domain from
its name, detect every misplaced class, or prove that a shared abstraction has
real consumers. Those remain source-structure review obligations. The configured
`*_rules.py` convention covers this project's language rule modules; other
projects should declare their own domain-specific placements.

## Shared JSON analysis across languages

Alias resolution and output forwarding now belong to shared semantic engines.
Python supplies its JSON and file/terminal API interpretation; JavaScript,
TypeScript and TSX supply the native `JSON.stringify`/`JSON.parse` interpretation.
All use the existing `type.broad` checker and `third_party_modules` policy.
Disabling `type.boundary` does not disable serialization checking or its boundary
evidence; disabling `type.broad` disables its JSON findings.

For JavaScript/TypeScript/TSX:

```javascript
const encode = JSON.stringify;
console.log(encode({ count: 1 }));
const body = encode({ count: 1 });
consume(body);
```

The console output is permitted; the encoding passed to `consume` is reported.

Recognized outputs are unshadowed `console.log/info/warn/error/debug`, standard
`process.stdout/stderr.write`, and imported `fs`/`node:fs` write/append file APIs
(including `fs/promises` and `node:fs/promises`). For filesystem APIs only the
payload argument establishes output; a serialized filename does not. Imports and
stable callable aliases preserve identity. Arbitrary methods named `write`,
shadowed globals, and imports from unrelated modules do not establish output.

Stable module aliases such as `const codec = JSON` are recognized. A JSON carrier
may pass through single-assignment locals or inline object/array values only if
every observed use reaches a proven output or configured library input. Decoder
aliases and internal consumers remain findings. A reassigned carrier cannot use
this exemption. Computed members, destructured aliases, runtime monkey-patching,
control-flow-sensitive reassignment, and cross-function value flow are not proved.
Go and Java also register serializer-specific adapters; their exact signatures
and output proofs are documented below.

## Configuring encoding APIs

Extend the existing `type.broad` checker to recognize third-party serializers and
project-approved output APIs. These lists add to the built-in behavior; empty or
omitted lists do not remove built-in encoders, decoders or output checks.

```json
{
  "checkers": {
    "type.broad": {
      "encoding": {
        "encoders": ["orjson.dumps", "@vendor/codec.encode"],
        "decoders": ["orjson.loads", "@vendor/codec.decode"],
        "outputs": [
          {"call": "transport.publish", "arguments": [1], "keywords": ["body"]}
        ]
      }
    }
  }
}
```

The [example policy](../examples/.codeharness/code-harness.json) contains a smaller
version of this configuration. Choose API names from the actual target project.

- `encoders`: exact qualified functions whose result is serialized data. Their
  results must flow exclusively to permitted outputs; registration is not an exemption.
- `decoders`: exact qualified reconstruction functions. Passing an encoding into
  these remains a finding, including via callable aliases or forwarded locals.
- `outputs`: exact `call` identities with payload selectors. `arguments` contains
  zero-based positional indexes; `keywords` contains Python keyword names. At least
  one selector is required. An empty selector list does not mean all arguments.

For the example output, `publish("topic", encoded)` and `publish(body=encoded)`
are permitted, while `publish(encoded, "payload")` does not establish an output
for `encoded`. Containers and forwarded locals use the existing all-consumers rule.
Comments do not shift argument positions. Positional offsets after `*args` or
`...args` are unknown and cannot establish a configured output; explicitly named
Python keywords still can. `**kwargs` is not inferred into named payload slots.

Names use resolved import identities, not local spellings. Python
`from orjson import dumps as pack` matches `orjson.dumps`; JavaScript/TypeScript
`import { encode as pack } from "@vendor/codec"` matches `@vendor/codec.encode`.
Stable callable/module aliases are followed. Names are exact and case-sensitive;
blank names, whitespace and wildcard patterns are rejected. Indexes must be
nonnegative integers, not strings or booleans. Unknown fields are errors, even
when `type.broad` is disabled.

The configuration uses the same shared rule in Python, Go, Java, JavaScript,
TypeScript and TSX. It does not install serializer libraries. Qualified API identities cannot
resolve arbitrary instance methods, computed members, dynamic imports or global
names without import/built-in evidence. APIs needing receiver-type or lifecycle
proof still need a language adapter. Declare functions returning serialized data
as encoders; in-place streaming encoders need separate API-specific interpretation.

`third_party_modules` remains an independent directional library-input policy.
A module need not be listed there to register its encoder or a precise output.
If an output's module is also configured third-party, the existing broader library
input exemption still applies independently of its payload selectors. Decoder
rejection always takes precedence over both output declarations and third-party
input exemptions. This configuration does not exempt `Any`, casts, or raw incoming
library results, and does not disable builtin round-trip protection.

### Source-owned instance output callbacks

All supported languages can explicitly approve a class-owned callback or
method (a named receiver type in Go) without treating every member with the same name as an output:

```json
{
  "checkers": {
    "type.broad": {
      "encoding": {
        "instance_outputs": [
          {
            "path": "src/analysis/command.ts",
            "class_name": "Cli",
            "member": "out",
            "arguments": [0]
          }
        ]
      }
    }
  }
}
```

This declaration permits `this.out(JSON.stringify(entry))` inside `Cli` in that
exact source snapshot. Function-valued properties such as
`private readonly out: (line: string) => void` are supported. The declaration is
an approval of the member's output responsibility, including injected
implementations; a callback signature alone does not establish actual I/O.
Review the injection contract and implementations before declaring the boundary.

This is a configured exception, not automatic proof of callable targets. The
checker does not follow assignments or injection sites to verify every possible
implementation. If the member can call either an allowed output or a forbidden
internal consumer, this declaration still approves the member call. Approve it
only when that trust is intended; review or remove it when the injection contract
or implementations change. This limitation applies to every language adapter.

Paths are exact, case-sensitive, normalized repository-relative POSIX paths,
matching the paths reported by the analyzer. Absolute paths, backslashes,
whitespace, wildcards, empty components, `.` and `..` are rejected. Class and
member names currently use ASCII JavaScript identifiers (including `$` and `_`).
A nonempty `arguments` list selects zero-based nonnegative integer positions;
booleans, strings, fractions, keywords and unknown fields are rejected. No
path/class/member pattern or whole-file exemption is supported.

For JavaScript, TypeScript and TSX, only direct `this.member(...)` calls within
instance methods or field initializers
are recognized. Nested arrows retain the enclosing instance; ordinary nested
functions, explicit TypeScript `this` parameters, object methods, static contexts,
getters/setters, decorated members,
computed members, inherited-only members, receiver aliases and extracted
callbacks do not establish this approval. The owning class must have one named
declaration in the snapshot, and the selected member must have one direct
instance declaration. Classes with computed or literal member names cannot establish an
unambiguous member identity. Parser-recovered snapshots fail closed.

Unmatched declarations are inert, with no separate configuration diagnostic.
This allows a shared policy during single-file and changed-file checks. Duplicate
class names or ambiguous members are also inert; they never select an arbitrary
owner. Audit actual matching sites when adopting or moving declarations. The language-specific forms below use the same exact selectors. Runtime rebinding of methods and dynamic
prototype mutation remain outside source-local lexical ownership analysis.

Every serialized carrier use must still reach an allowed output. Conditional
result branches can forward the value, including
`this.out(json ? JSON.stringify(entry) : text)`; conditions themselves do not
forward it. Other payload positions, unknown positions after spreads, internal
consumers, transforms and reconstruction remain findings. Existing builtin and
imported output recognition and decoder precedence are unchanged. This approval
does not exempt broad annotations, assertions or incoming library data.

The contract and selector matching belong to shared encoding semantics. The
JavaScript adapter owns lexical `this`, member declarations and static/dynamic
context checks. Conditional result flow belongs to the JavaScript semantic
adapter and also applies to existing outputs. Ownership/import policy paths
already cover these modules; no gate exclusions or limits need adjustment.

#### Python

Declare the source path, class and direct method or callback field. The actual
first positional instance parameter establishes ownership; its name need not be
`self`. Calls such as `self.out(json.dumps(entry))`, including conditional result
branches and closures capturing that same binding, can use the approval. Fields
may be declared on the class or initialized on the instance in `__init__`.

Decorated methods (including static/class methods and properties), variadic
receivers, reassigned/shadowed receivers, receiver aliases, inherited-only
members and duplicate declarations do not establish approval. Python keyword
payloads are not inferred from positional selectors: `self.out(line=encoded)`
remains checked. Existing qualified `outputs` declarations still support Python
keyword selectors.

#### Go

Use `class_name` for the named struct receiver type, `member` for its direct
method or function-valued field, and the exact file containing that type and
receiver method. For example, `Cli` / `out` approves `c.out(data)` from
`func (c *Cli) run(...)` when `out` is directly declared on `Cli`. Pointer/value
receivers and closures capturing the unchanged receiver are supported. Embedded
or nested fields, receiver aliases/reassignment, ordinary function parameters
and uncertain ownership remain checked.

Imported `encoding/json.Marshal` and `encoding/json.MarshalIndent` are native
encoders; `encoding/json.Unmarshal` is a decoder. Import aliases and stable
callable aliases preserve identity. For `data, err := json.Marshal(value)`, only
`data` is the serialized carrier: checking or reporting `err` is independent.
Every observed use of the single-assignment data binding must reach output.
This two-target, single-RHS shape is explicit; multi-assignment inference is not
applied to arbitrary configured encoders. Predeclared/reassigned carriers,
aggregate result forwarding, byte/string transformations and streaming encoder
lifecycles remain outside this proof. Configured encoder APIs otherwise describe
single serialized return values.

Recognized Go terminals include imported `fmt.Print`/`Println`,
`os.Stdout.Write`/`os.Stderr.Write` payload 0 and `os.WriteFile` payload 1. Arbitrary
writer methods and memory buffers do not become outputs from their spelling.

#### Java

Direct `this.out(encoded)` requires one directly declared instance method.
`this.out.accept(encoded)` can approve the field named `out` when its declared
type is explicitly imported `java.util.function.Consumer`. Its payload positions
refer to `accept` arguments. This supports injected callbacks without granting
every `accept` method an exemption. Lambdas preserve the enclosing `this`.
Static contexts/fields/methods, anonymous classes, inherited-only methods,
overloads, duplicate fields, extracted callbacks and other receivers remain
unproved. Implicit receiver calls and compiler overload selection are not inferred.

Imported/declared receiver types identify one-argument `Gson.toJson`,
`ObjectMapper.writeValueAsString` and `writeValueAsBytes`. Their corresponding
`Gson.fromJson` and `ObjectMapper.readValue`/`readTree` consumers reject
reconstruction. Explicitly typed locals, parameters, fields and direct
constructors can establish the library receiver; a method named `toJson` alone
cannot. Gson's multi-argument overloads include streaming APIs and are not
classified automatically without overload proof. Fully qualified type syntax,
`var` inference, arbitrary serializer subclasses and streaming lifecycles are
not claimed by this adapter. Exact configured imported/static API identities
are also supported.

`System.out`/`System.err` `print` and `println` recognize payload 0, subject to
shadowing checks. Local variable initializers and conditional result branches
retain all-consumer flow. The encoded value used as a condition, in another
argument, or by an internal consumer still produces a finding.

Custom Python construction uses `BroadTypeOptions(encoding=EncodingOptions(...))`
inside `Checkers(type_broad=...)`; use `BroadTypeOptions(enabled=False)` to disable
that checker. `CheckerOptions` remains the concrete option type for checkers without
additional settings. JSON `enabled` settings retain their existing behavior.

These declarations are project policy, not proof that an API performs I/O. Review
the actual API contract and payload positions before adding an output. Normal
policy review and staged-policy safeguards apply. No project exclusions or checker
thresholds need to change to adopt this configuration.

## Checker-owned registration

`Checkers` explicitly composes typed configuration fragments. It declares no
checker fields or checker-name list itself. Owners declare their concrete options,
configuration key and diagnostic mapping beside the associated checker contracts:

| Owner | Configuration |
| --- | --- |
| Function measurements | `metrics/options.py` |
| Architecture checks | `architecture/options.py` |
| Serialization checks | `semantics/encoding_options.py` |
| Boundary and usage checks | `semantics/options.py` |
| Shared type and syntax switches | `policy/type_options.py` |

`policy/contracts.py` owns strict, frozen base contracts and `CheckerDefinition`.
Each fragment declares concrete Pydantic fields, derives JSON aliases from its
checker definitions, and contributes `CheckerState` values through cooperative
`checker_states()` composition. A state contains only identity, diagnostic mapping
and an enable flag. Option payloads remain in their original concrete fields;
there is no heterogeneous option store, cast, dynamic model or serialization step.

`disabled_checkers()` and `disabled_rules()` consume those states uniformly.
`function_size` declares its five diagnostic IDs at its owner; it needs no special
branch in shared policy code. Rule implementations and built-in requirement
profiles reference the same definitions. Validation rejects duplicate names,
empty/duplicate diagnostic IDs, overlapping diagnostic ownership and differences
between registered checker names and the composed schema's field aliases.

A new checker contributes a typed fragment and adds that fragment to the explicit
application composition. Its schema, defaults and disabled-diagnostic expansion
then participate automatically. Runtime discovery of arbitrary checker schemas is
outside this API. Each overriding `checker_states()` must include
`super().checker_states()`; the field-registration invariant rejects omissions.

Policy JSON, the Python option constructors and imports from `policy.models`
are supported. That module owns composition and re-exports canonical option
classes rather than defining them. Package-level `MetricRule`
and `ArchitectureRule` exports load their concrete implementations lazily, so
importing checker contracts does not create an execution-to-policy import cycle.

`policy/contracts.py` holds the leaf contracts and imports no application modules.
The composition module imports owner contracts, and runtime checkers consume their
owner's definitions and concrete policy fields.
