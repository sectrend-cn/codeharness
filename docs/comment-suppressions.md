# Approved next-line diagnostic exceptions

Python, Go, Java, JavaScript, JSX, TypeScript and TSX support a standalone line
comment using the language's own marker: `#` for Python and `//` for Go, Java and
the JavaScript family.

```ts
// code-harness: ignore-next-line type.broad -- Serialized test input.
const input = JSON.stringify(payload);

// code-harness: ignore-next-line type.broad -- Expected wire response.
assert.equal(result.content, JSON.stringify(expected));
```

```python
# code-harness: ignore-next-line type.annotation -- Legacy adapter boundary.
value: object = read_payload()
```

```go
// code-harness: ignore-next-line type.broad -- Generated wire payload.
type Payload any
```

```java
// code-harness: ignore-next-line type.broad -- Framework callback signature.
void handle(Object value) { consume(value); }
```

Use this only for an explicitly approved exception. The nonblank reason records
human approval; it is not proof of safety. Reviewers must reconsider the exception
when the code changes purpose. Independently of this mechanism, a shared set of
foreign directives stays prohibited: `noqa`, `type: ignore`, `pyright: ignore`,
`mypy: ignore`, the `@ts-ignore` family, the `eslint-disable` family, `nolint`
and `lint:ignore` are reported as `type.suppression` in every supported language.
`NOSONAR`, `CHECKSTYLE:OFF`, `noinspection` and the
`@SuppressWarnings`/`@SuppressFBWarnings` annotations are Java-only detection,
reported there by the Java comment and annotation policy path described below.

The selector must be one exact diagnostic ID registered for the source's analyzer,
including metric IDs such as `size.lines` rather than the `function_size` checker
configuration key. Unknown IDs, wildcards, lists and `type.suppression` itself are
invalid. No configuration switch, approval-file loader or hash is involved.

Only findings with the exact source path, immediately following physical line,
and diagnostic ID are omitted from the normal findings collection. Every matching
finding on that line is covered. Other rules and lines remain active. In particular,
`type.broad` also covers broad annotations: `unknown` or `any` on the target line
is suppressed along with encoding findings. Split mixed-purpose lines before
annotating if approval covers only encoding. Multiline expressions are covered
only where diagnostics start; a nested encoder starting later needs its own
comment. Blank lines and other comments are never skipped.

Only actual parser comment nodes are considered. Strings and template-literal
text cannot suppress anything. Trailing directives, block comments (Go, Java and
the JavaScript family `/* ... */`; Python has no block comment form), file-wide
forms, missing reasons and malformed syntax produce `type.suppression`. A valid
directive with no matching diagnostic on its target produces the same error.
Existing per-checker enable flags still apply: a disabled rule emits no findings,
so a directive selecting it is unused when suppression validation is enabled.
The report schema, checker execution and native exit semantics are unchanged.

Java keeps its own comment and annotation policy path alongside this mechanism.
A valid directive whose reason cites `NOSONAR`, `CHECKSTYLE:OFF` or `noinspection`
(case-insensitive) reports one additional `type.suppression` finding on the
directive line while still suppressing its target. That finding comes from the
independent Java disabled-types check, so the directive cannot suppress it. Keep
such markers out of the reason; the reason field only records approval.

## Snapshot and scope behavior

The analyzer reads comments from the same immutable source snapshot it checks.
Staged audits use index blobs; adding or removing a disk-only comment cannot
change a staged result. Comment additions select the following target before
expanding affected definitions/statements. Deletion/replacement hunks containing
a removed `code-harness:` marker conservatively select the following boundary;
this textual scope hint cannot authorize suppression. Parser evidence from the
current audited snapshot alone determines which directives are valid.

Unused-directive validation runs only when the target is in the selected scope.
A target edit can therefore expose a stale directive just outside that scope,
while an unrelated partial audit does not report false unused directives.

## Ownership and verification

`languages/comments.py` owns the single shared, parameterized directive syntax.
Each consumer supplies that grammar's comment node types and line marker, and the
shared implementation walks the syntax tree itself, so grammars with distinct
line and block comment node types are filtered correctly. Application composition
(`plugins/builtins.py`) binds Python `({"comment"}, "#")`, Go
`({"comment"}, "//")`, Java `({"line_comment", "block_comment"}, "//")` and the
JavaScript family `({"comment"}, "//")`. The former
`languages/javascript/comments.py` adapter is removed; the JavaScript family uses
the same shared implementation, which keeps the supported languages behaviorally
identical by construction. Shared `suppressions.py` owns the concrete selector
contract, syntax and registered-ID validation, usage validation and exact
diagnostic filtering; it did not change when the mechanism expanded. Application
composition opts in compatible analyzers; shared analysis has no language
identity dispatch. `analysis/scopes.py` expands supplied target lines;
`snapshots.py` retains conservative diff scope hints. Existing ownership and
import policies cover these modules without configuration changes.

`tests/test_line_suppressions.py` covers approved inputs/assertions, multiple and
nested encoders, exact rule/path isolation, broad annotations, invalid selectors,
blank/comment targets, parser literal isolation, stale directives, partial scope
and CRLF/indentation for the JavaScript family, and the same acceptance,
rejection, literal, stale and scope behavior for Python, Go and Java, including
block-comment rejection, per-language registered-rule selection and the Java
foreign-marker reason case. CLI regressions in `tests/test_cli.py` cover
additions, removals and replacements in both changed modes plus disk/index
isolation for the JavaScript family, the full Python matrix and sampled Go and
Java operations.

## Local validation (2026-10-27)

Required static checks passed: `uv run --no-sync mypy src tests`,
`uv run --no-sync ruff check src tests`, and
`uv run --no-sync ruff format --check src tests`.

A focused branch-coverage run used cached Coverage.py without changing project
dependencies:

```sh
uv run --no-sync --offline --with coverage python -m coverage run --branch \
  --data-file=/tmp/code-harness-suppression.coverage --source=code_harness \
  -m pytest -q tests/test_line_suppressions.py tests/test_cli.py \
  tests/test_checker_options.py tests/test_extensions.py tests/test_gate.py
```

All 326 focused tests passed. Statement and branch coverage were 100% for
`suppressions.py`, `languages/comments.py`, and `analysis/analyzer.py`.
Across those modules plus scopes, composition and snapshots, combined coverage
was 95%. Missing statements were the pre-existing full-scope fallback in
`scopes.py` (`lines` only runs in changed modes), snapshot failure paths, and the
compatibility parser facade in `plugins/builtins.py` that these tests never call.
This is bounded local coverage, not consumer migration or CI execution evidence.

Final full validation: `uv run --no-sync pytest -q` passed all 1,662 tests.
`uv run --no-sync code-harness --all` exited 0 across 168 files with no errors
and 56 existing `unused.return` warnings on unchanged call sites: 28 from `_git`
calls in `tests/test_cli.py`, the rest from `tests/test_review_submissions.py`
(12), `tests/test_acp_review.py` (7), `tests/test_plugins.py` (6),
`tests/test_extensions.py` (2) and `src/code_harness/review/acp.py:81` (1). No
ownership configuration changes, suppression comments on authored implementation
code, consumer migration, commit or publication were performed.
