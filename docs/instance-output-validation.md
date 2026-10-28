# Scoped instance output validation — 2026-10-12

This records the initial JavaScript-family implementation checkpoint.
The subsequent [language extension](instance-output-language-extension.md) adds
Python, Go and Java support and records the current validation results.

`type.broad.encoding.instance_outputs` approves an exact path, class, member and
positional payload slot for output sites that qualified-import API matching
cannot recognize, such as `Cli.out(JSON.stringify(...))` calls. See
[configuration and inference limits](checker-configuration.md#source-owned-instance-output-callbacks).

## Ownership and review

- Shared encoding semantics own the strict `InstanceOutput` contract and exact
  source/class/member/argument matching. The existing `SemanticIndex` remains
  the canonical owner of source scopes; no parallel AST or untyped carrier is added.
- The JavaScript encoding adapter owns lexical `this` interpretation, member
  declarations, and rejection of dynamic, static or ambiguous receiver contexts.
  It supports JS, TS and TSX. Other adapters return no instance ownership proof.
- The JavaScript semantic adapter recognizes conditional result branches as
  value containers. Conditions do not forward a value. Shared `ValueFlow` still
  requires every observed use of a single-assignment carrier to reach output.
- Existing ownership and import boundaries cover both new modules. The tool's
  active policy, exclusions, thresholds and dependencies are unchanged.
- Explicit declarations assign output responsibility to the configured callback,
  including its injected implementations. They do not prove runtime I/O or
  dynamic method/prototype behavior. Unsupported or ambiguous declarations are
  inert and retain findings; malformed declarations are configuration errors.

## Requirement and regression evidence

| Requirement or risk | Behavioral evidence |
| --- | --- |
| Default behavior and unrelated broad types | Paired configured/default tests |
| Exact file, class and member identity | Other files/classes/members, duplicate classes, inherited-only members, anonymous classes and literal/computed duplicates |
| Receiver ambiguity | Nested ordinary/generator functions, object methods, static members/blocks/fields, getters, aliases, private syntax, explicit TS `this`, parser recovery |
| Precise payload slots | Positions zero and one, other arguments, comments, parentheses and unknown spread offsets |
| Internal flow and reconstruction | Mixed output/internal reads, alias chains, reassignment, transforms, decoder calls, conditional conditions and branches |
| Existing outputs and custom APIs | Existing console, stream, filesystem, Python and configured encoder/decoder regression suites |
| Strict configuration | Missing selectors, malformed paths/names, empty indexes, negative/fractional/string/boolean indexes and unsupported fields |

## Executed checks

- `uv run --no-sync code-harness --all`: 148 files, zero errors, 47 existing
  discarded-return warnings. The native warning-only exit status is zero.
- `uv run --no-sync mypy src tests`: passed, 147 source files.
- `uv run --no-sync ruff check src tests`: passed.
- `uv run --no-sync ruff format --check src tests`: passed, 148 files.
- `uv run --no-sync pytest -q`: **1,201 passed**.
- Focused encoding suites: **435 passed** with branch coverage enabled using
  an isolated `uv run --no-sync --with coverage` environment. Both new
  `encoding_members.py` modules, `semantics/encoding.py` and
  `semantics/encoding_options.py` have **100% statement and branch coverage**:
  168 statements, 48 branch destinations, no missing or partial branches.
  Changed adapter/conditional-flow lines execute in the focused suites; this is
  not a claim of complete coverage of the existing semantic adapter.
- `git diff --check`: passed.
