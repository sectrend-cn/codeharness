# `unused.parameter`

[Back to the checker index](../checkers.md)

Reports declared parameters without resolved read usage.

**Severity**: error.

**Languages**: every analyzer. Python `self`/`cls`, JavaScript `this` and blank
`_` bindings are not candidates. Positional arguments match by position,
keyword-only arguments by name, and variadic slots separately. Methods linked by
resolved inheritance share parameter-use evidence: a read in any implementation
makes the corresponding parameter used throughout its override family, including
base and sibling implementations and imported bases; extra arguments and
parameters unread throughout the family remain findings, and unrelated
same-named methods do not gain the exemption. Structural interface relationships
without resolved inheritance still need review. Required signature constraints
should be explained rather than fixed by deleting a parameter.

**Options**: None beyond `enabled` (boolean, default `true`).

Correct:

```json
{
  "checkers": {
    "unused.parameter": {"enabled": false}
  }
}
```

Incorrect — unknown option:

```json
{
  "checkers": {
    "unused.parameter": {"ignore_prefix": "_"}
  }
}
```
