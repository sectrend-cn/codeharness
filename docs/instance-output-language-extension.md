# Scoped output extension to Python, Go and Java

## Implementation proposal

Retain the existing exact path, class/type name, member and positional-payload
contract. Grammar adapters prove the receiver and directly declared member;
shared semantics continue to match configuration and enforce all-consumer flow.

- Python: approve calls on the actual first instance-method parameter, including
  captured receivers in nested functions. Reject decorated/static/class methods,
  shadowed or reassigned receivers, other objects, inherited-only and duplicate
  members. Support methods and callback fields declared or initialized on the
  instance. Forward conditional result branches, never their condition.
- Go: use `class_name` for the named receiver type in the same source file.
  Approve direct receiver methods and function-valued struct fields; reject
  aliases, embedded/promoted fields and uncertain receiver/type ownership.
  Wire the encoding rule into the Go type rule, recognize imported
  `encoding/json.Marshal`/`MarshalIndent`, and track only the first byte result
  of an exact two-target assignment. Error-result uses do not consume the payload.
- Java: wire the encoding rule into the Java type rule. Recognize serializers
  through exact imported API identities and declared library receiver types.
  Approve explicit `this.member(...)` methods and `this.callback.accept(...)`
  only for a declared `java.util.function.Consumer` field. Reject static,
  inherited-only, overloaded/ambiguous, anonymous-class and shadowed receivers.
  Preserve actual invocation argument positions and conditional value flow.

Tests must pair approved and unapproved cases, exercise exact file/type/member
scope and wrong slots, and retain internal-use, mixed-use, reconstruction and
unresolved-owner findings. Existing JS/TS/TSX behavior must remain unchanged.
No exclusions, checker disabling, broad payload carriers or suppression comments
are part of this extension.

Recognition remains source-local; it does not claim compiler overload dispatch,
runtime injection behavior, dynamic descriptors/prototype mutation or arbitrary
streaming serializers. Actual coverage and unsupported forms will be recorded
with the final checks rather than inferred from shared infrastructure.

## Implemented contracts and API evidence

The implementation follows the proposal using the existing `EncodingRule`,
`QualifiedNames`, `SemanticIndex`, `ParameterSlot` and `ValueFlow` contracts.
Language adapters own invocation shape, receiver proof, native serializer
signatures and conditional result syntax. Shared code contains no language
identity dispatch. No ownership paths, checker limits or exclusions changed.

Python and JS/TS/TSX retain existing serializer recognition. Go and Java now
compose `EncodingRule` into their concrete type rules, preserving one owner for
`type.broad`. Custom construction of `GoTypeRule` or `JavaTypeRule` must supply
that rule, as already required for Python and TypeScript type-rule construction.

Go's [Marshal contract](https://pkg.go.dev/encoding/json#Marshal) returns bytes and
an error; the adapter tracks the proven first binding of a two-target assignment
and checks every observed payload use. It does not exempt a payload because its
sibling error reaches a logger. General multi-result inference, predeclared or
reassigned carriers, conversions and streaming lifecycles remain unproved.

Java's imported [Consumer contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Consumer.html)
identifies the callable `accept` member, while the explicit policy owns the
callback's output responsibility. The [Gson API](https://javadoc.io/static/com.google.code.gson/gson/2.11.0/com.google.gson/com/google/gson/Gson.html)
has both returned-string and streaming `toJson` overloads; native recognition
therefore covers the unambiguous one-argument form. The selected
[ObjectMapper APIs](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-databind/2.17.3/com/fasterxml/jackson/databind/ObjectMapper.html)
are `writeValueAsString`/`writeValueAsBytes`, with `readValue`/`readTree` rejecting
reconstruction. These are selected signature adapters, not a claim of coverage
for every library version, overload, subtype or streaming API.

See [configuration](checker-configuration.md#source-owned-instance-output-callbacks)
for exact supported syntax and unproved cases. No type erasure, casts, comments
suppressing checks, or broad callback carriers were introduced.

## Validation — 2026-10-12

- `uv run --no-sync code-harness --all`: **155 files, zero errors, 47 existing
  discarded-return warnings**. The native warning-only exit status is zero.
- `uv run --no-sync mypy src tests`: passed, 154 files.
- `uv run --no-sync ruff check src tests`: passed.
- `uv run --no-sync ruff format --check src tests`: passed, 155 files.
- `uv run --no-sync pytest -q`: **1,316 passed**.
- The five focused encoding/instance-output suites pass **550 tests**. Branch
  coverage uses an isolated `uv run --no-sync --with coverage` environment;
  project dependencies and lockfiles are unchanged. Selected encoding/flow
  modules have **95% combined coverage** over 553 statements and 180 branch
  destinations. Shared encoding matching is 100%; new receiver adapters measure
  Python 93%, Go 97%, Java 95%; Java serializer/type recognition is 100%.
  Missing paths were inspected: they include conservative unsupported assignment,
  absent-body, receiver-position and traversal guards. This does not claim full
  repository or compiler-semantic coverage.
- `git diff --check`: passed.

Regression coverage pairs declared and undeclared outputs and checks exact paths,
classes/types and members; constructor callbacks; captured lexical receivers;
conditional results versus conditions; internal/mixed/reconstructed carriers;
wrong positional slots; imported and configured APIs; standard terminal APIs;
serializer-name shadowing; static/decorated/overloaded/inherited members; grouped
duplicate declarations; Python variadic receivers; and Go payload/error separation.
Existing JavaScript-family and Python encoding regression suites remain passing.
