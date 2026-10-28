# Guarded field projections

`structure.guarded_projection` is an error-level maintainability rule enabled by
default for Python, Go, Java, JavaScript/JSX, TypeScript and TSX. It reports repeated
conditional copying independently of function complexity. It does not prove a
runtime defect or that a guard can safely be removed.

The strict configuration accepts `enabled` and `min_fields` only. The threshold
is an inclusive integer, at least 2, default 3; booleans, strings and fractional
numbers are rejected. For example:

```json
{
  "checkers": {
    "structure.guarded_projection": {"min_fields": 4}
  }
}
```

Omit the entry to use defaults. Set `enabled: false` to disable the checker across
languages; reports disclose its disabled name through the existing contract.

## Language coverage

| Language | Predicates | Projection syntax |
| --- | --- | --- |
| JavaScript, TypeScript, TSX | Built-in `undefined` with `===`/`!==`; nullish `null` with `==`/`!=`; strict equality to boolean, number or string literals | Guarded assignments; ternary or `&&` single-property object spreads |
| Python | `None` with `is`/`is not` or `==`/`!=`; literal equality with `==`; boolean identity with `is` | Guarded attribute or literal-string-key assignments; conditional dictionary unpacking |
| Go | Unshadowed `nil` with `==`/`!=`; equality to unshadowed booleans, numbers or strings | Guarded selector assignments |
| Java | `null` with `==`/`!=`; equality to boolean, number, character or string literals | Guarded field assignments |

Signed numeric literals are supported. String recognition is conservative: plain
quoted literals and Go raw strings without escapes or newlines are recognized;
triple quoting, interpolation and escape decoding are not inferred. Go map indexing, Java
accessors/setters and collection calls are outside the initial field contract.
There is no conditional object-spread syntax claimed for Go or Java.

For absence/null checks, the active branch can be inverted with an empty opposite
branch. Python `pass` is empty. Presence, nullishness and literal equality remain
distinct in diagnostic evidence. Literal guards may write the established literal
or copy the same source field. Truthiness, compound predicates, arithmetic,
conversion, validation, early exits and business operations are excluded.

JavaScript examples of the same pattern:

```ts
if (source.a !== undefined) target.x = source.a;
if (source.b === undefined) {} else target.y = source.b;
if (source.c === true) target.z = true;

const result = {
    ...(source.a === undefined ? {} : {x: source.a}),
    ...(source.b !== undefined ? {y: source.b} : {}),
    ...(source.c === true && {z: true})
};
```

These produce two findings with the default threshold. Property renaming,
parentheses, braces, optional chaining and literal string bracket access preserve
recognition. Literal computed object keys are supported in JavaScript; dynamic
dictionary/object keys are excluded. Python attribute access and item lookup
retain different identities, including nested receivers and destination fields;
only one scalar string subscript is supported. Tuple and multidimensional indexes
are excluded. JavaScript object-literal `__proto__: value` entries set a prototype
and do not contribute copied properties; computed `["__proto__"]: value` entries
remain ordinary properties.

## Regions and identities

A cluster is a consecutive sequence within one statement block, the Python
module body, the JavaScript, TypeScript and TSX top-level program body, or one
literal, sharing one source receiver and one destination binding/construction.
Comments and empty statements are ignored. Other statements, ordinary properties,
unrelated spreads, different receivers or different destinations end the cluster.
Repeated writes to the same destination field count once.

Nested functions, loops, branches and nested objects have their own regions. No
cluster crosses a call, reassignment, control-flow join or separate literal. A
qualifying cluster inside a loop or nested function can still be reported.

Receiver identity uses the existing lexical semantic index and static member
paths. JS/TS/TSX `const` identifier aliases are followed only with a preceding
single initializer and no reassignment of the referenced binding. Mutable aliases
are not equated with their sources. Python/Go/Java aliases retain their own lexical
identity. Property-initialized locals such as `const usage = response.usage` retain
their local binding; the checker does not equate them with repeated property reads.
Unresolved bindings, dynamic property paths, method-call receivers and alias
cycles do not establish identity. This is local evidence, not whole-program alias
or getter analysis.

One finding is anchored at the first guard/spread and records distinct field
count, receiver, destination, participating `line:column` locations and predicates.
The report schema is unchanged. Complexity findings can coexist. Existing changed
definition selection and staged snapshot isolation remain in effect.

## Contract review and remediation

Review the source/destination contracts and mapping owner first. Preserve field
types, omission, evaluation order and exceptions. Where required nullable fields
are the actual domain contract, a concrete object can express the mapping. Where
omission is required, retain it through reviewed typed construction or change the
owning contract and its consumers together.

Do not disable `exactOptionalPropertyTypes`, add `| undefined` solely to silence
the rule, use erased dictionaries/casts/serialization filtering, or create one
forwarding helper per field. Turning assignments into conditional spreads does
not remove the pattern. Repeated validation of already typed internal fields is
not remediation. No autofix or filename-based exemptions are provided.

## Ownership and extension

`semantics/projection/` owns the concrete options, original-node evidence,
binding matcher and clustering policy. Language owners implement
`ProjectionSyntax`; `languages/projection_syntax.py` shares grammar operations,
and each language supplies its predicate and construction interpretation.
`plugins/builtins.py` supplies those capabilities and requires the diagnostic for
every built-in language. New languages must supply equivalent adapters and
behavioral fixtures before claiming coverage.

The existing semantic owner and import/extension paths cover the new package.
Language code cannot import the projection rule implementation. Shared matching
imports no language implementation, selects no language identity, retains the
canonical tree-sitter nodes and lexical index, and adds no generic AST or payload
carrier. Catch and destructuring declarations are owned by JavaScript's existing
binding adapter so built-in `undefined` checks respect those scopes.

## Validation evidence — 2026-10-10

Behavioral suites cover threshold boundaries, strict options, disabling, all six
language variants, literal equality, inverted branches, aliases and shadowing,
distinct fields, interruptions, nested scopes, negative operations and all CLI
modes. `test_motivating_function_preserves_two_destinations_and_complexity`
asserts the proposal's 7-assignment and 3-spread findings and independent complexity
reporting. CLI tests compare source, policy and index bytes before/after execution.

Saved-source validation completed:

| Command | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` | 145 files; zero errors and the same 47 warnings as the original 130-file baseline |
| `uv run --no-sync mypy src tests` | Passed; 144 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed; 145 files |
| `uv run --no-sync pytest -q` | 1,061 passed |
| `git diff --check` | Passed |

The five projection suites contain 191 passing cases. Branch coverage collected
with an existing cached Coverage.py installation (no dependency changes) reports
96% combined statement/branch coverage across the new projection implementation:
473 of 486 statements covered, with 14 partial branches among 158 branches.
Shared clustering has 100% coverage. Remaining gaps include malformed-tree
rejections, unsupported predicate/literal forms, cycle defense and parenthesized
destination labels; this does not claim exhaustive semantic coverage.

## Focused defect review — 2026-10-10

Three confirmed matcher defects were reproduced and corrected:

- Python `source.a` and `source["a"]` were incorrectly equated, including nested
  receivers and destination counts. Canonical `FieldKey` evidence now preserves
  the access operation through matching, receiver paths and clustering.
- Python subscripts with multiple keys or a trailing comma were reduced to their
  first key. These are tuple indexes, possibly with additional operations; the
  adapter now rejects them as scalar field evidence.
- JavaScript/TypeScript/TSX object-literal prototype setters were counted as
  enumerable fields contributed by a spread. Noncomputed `__proto__` entries now
  end the cluster, while computed keys remain supported.

`test_projection_access_identity.py` adds 26 regression cases: 22 failed before
these fixes and all 26 pass afterward. It covers mismatched and matching reads,
nested source/destination identities, distinct destination access operations,
three tuple-index positions and all three script language variants. An earlier
positive Python fixture was corrected to copy the same dictionary item it guards.
