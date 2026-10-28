# TypeScript constructor parameter-property usage

Constructor parameters marked `public`, `protected`, `private` or `readonly`
can declare instance properties. `unused.parameter` now accepts resolved reads
of those properties as usage of the exact constructor parameter declaration.
Initialization and writes alone remain insufficient. Ordinary parameters and
unrelated declarations with the same name remain reportable.

## Ownership and scope

`languages/typescript/semantic_syntax.py` owns modifier recognition, abstract
class syntax, positive `instanceof` guards and conditional expression branches.
The shared `Scope.parameter_properties` table associates each instance member
with its canonical parameter `Symbol`, retaining the original tree-sitter node
and diagnostic location. Properties are separate from lexical bindings, so an
unqualified same-name outer variable does not become a property read.

`semantics/parameter_properties.py` resolves receiver and declaring-class
identities, including imported and inherited members. Derived declarations stop
base-member lookup. Guard evidence requires the same lexical binding and no
intervening recorded write. Conditional receivers require agreeing class
identities; ambiguous owners remain unresolved.

`ProjectUsage` builds a separate property evidence graph over the existing
parsed snapshots. All indexes in that graph are isolated, including imported
peers, and only used parameter declaration IDs are returned through the existing
usage-evidence contract. This adds a semantic indexing/linking pass without
reparsing source. Enhanced abstract-class and lexical-base resolution therefore
do not change function, field or discarded-return evidence in the main graph.
`UsageRule` retains its existing diagnostic policy and occurrence locations.

The existing language, semantic and composition owners and dependency boundaries
cover these files. No configuration, exclusion, suppression, type-erasure
exception or diagnostic severity changed.

This is bounded syntax and symbol evidence, not TypeScript compiler analysis.
Dynamic/computed property accesses, arbitrary aliases and more complex control
flow are not established by this change. The enhanced graph intentionally does
not extend return-type inference for other rules.

## Regression evidence

`tests/test_typescript_parameter_properties.py` adds 58 cases covering TS and
TSX modifiers, `this`, inherited and external reads, imported generic classes,
optional/default parameters, abstract classes, positive guards and conditional
receivers. Negative cases cover unread and write-only properties, ordinary and
destructured constructor parameters, unrelated members, nested classes, local
and method-parameter shadowing, guard scope and receiver reassignment. A separate
assertion preserves existing discarded-return diagnostics.

Final local validation on 2026-10-13:

| Check | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` | Exit 0; 160 files, 47 warnings, zero errors |
| `uv run --no-sync mypy src tests` | Passed; 159 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed; 160 files |
| `uv run --no-sync pytest -q` | 1430 passed |
| Property, semantic usage/resolution and override tests | 167 passed |
| `git diff --check` | Passed |

Branch coverage used cached `coverage==7.13.4` with the 167 focused cases. The
new syntax and evidence modules execute 117/124 statements (94.35%) and 54/62
branches (87.10%). Remaining gaps are defensive incomplete-node checks, cycle
protection, missing-member exits and an unresolved guard target. Shared changed
registration, declaration and graph-construction lines execute; unsupported
language guard/conditional defaults remain unexercised by this focused suite.
Coverage artifacts are `/tmp/parameter-property-final-coverage.xml` and
`/tmp/parameter-property-shared-coverage.xml`.
