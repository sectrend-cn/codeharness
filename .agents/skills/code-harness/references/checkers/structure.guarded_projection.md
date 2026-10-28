# `structure.guarded_projection`

[Back to the checker index](../checkers.md)

Reports repeated conditional copying of destination fields in one consecutive
local region. It is an error-level maintainability finding: it does not prove a
runtime defect, and it does not prove that a guard can safely be removed or
replaced by a spread.

**Severity**: error.

**Languages**: every analyzer. Region shape, recognized predicates and
projection syntax differ:

| Language | Regions | Predicates | Projection syntax |
| --- | --- | --- | --- |
| JavaScript, TypeScript, TSX | Blocks and the top-level program body | Built-in `undefined` with `===`/`!==`; nullish `null` with `==`/`!=`; strict equality to boolean, number or string literals | Guarded assignments; ternary or `&&` single-property object spreads |
| Python | Indented blocks and the module body | `None` with `is`/`is not` or `==`/`!=`; literal equality with `==`; boolean identity with `is` | Guarded attribute or literal-string-key assignments; conditional dictionary unpacking |
| Go | Statement lists | Unshadowed `nil` with `==`/`!=`; equality to unshadowed booleans, numbers or strings | Guarded selector assignments; no conditional spread form |
| Java | Method and constructor bodies | `null` with `==`/`!=`; equality to boolean, number, character or string literals | Guarded field assignments; no conditional spread form |

A cluster is a consecutive sequence within one statement block, the Python
module body, the JavaScript, TypeScript and TSX top-level program body, or one
object literal, sharing one source receiver and one destination binding or
construction. Comments and empty statements are ignored. Other statements,
ordinary properties, unrelated spreads, different receivers or different
destinations end the cluster, and repeated writes to the same destination field
count once. Nested functions, loops and branches have their own regions. Signed
numeric literals are supported; triple-quoted strings, interpolation and escape
decoding are not inferred. Go map indexing, Java accessors/setters and
collection calls are outside the field contract. Dynamic computed keys are
excluded, and JavaScript `__proto__: value` entries set a prototype instead of
copying a property.

**Options**: `enabled` (boolean, default `true`); `min_fields` (integer, at least
2, default 3). The threshold is inclusive and counts distinct destination fields;
booleans, strings and fractional numbers are rejected.

Correct:

```json
{
  "checkers": {
    "structure.guarded_projection": {"min_fields": 4}
  }
}
```

Incorrect — an unknown option and a threshold below the minimum are both
rejected:

```json
{
  "checkers": {
    "structure.guarded_projection": {"minimum_fields": 4, "min_fields": 1}
  }
}
```
