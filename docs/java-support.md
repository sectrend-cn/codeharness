# Java support

Java `.java` files participate in full, staged and base-selection audits through
the standard language registry. Parsing uses the locked `tree-sitter-java` grammar;
no JDK or build is needed. The gate preserves the source snapshot and original
locations. Recovered syntax produces warnings and still permits syntax checks;
usage and boundary diagnostics require a complete parse.

## Checked behavior

| Area | Java evidence |
| --- | --- |
| Function metrics | Methods, constructors, compact record constructors and lambdas; receiver parameters excluded, varargs counted once |
| Control metrics | Branches, loops including enhanced `for`, catches, non-default switch labels, ternaries and short-circuit operators; nested lambdas measured independently |
| Broad types | `Object`/`java.lang.Object`, unbounded `?`, recognized raw standard collections with explicit import or qualified-name evidence |
| Assertions | Reference casts; primitive numeric/boolean casts are permitted |
| Suppressions | `SuppressWarnings`, `SuppressFBWarnings`, `NOSONAR`, `CHECKSTYLE:OFF`, `noinspection` and shared comment directives |
| Imports | Qualified type imports, static member imports and wildcard import targets passed to architecture policy |
| Object design | Identity comparisons and switches, including string `equals` comparisons; Java has no module-level functions |
| Usage | Explicit parameters, private methods, fields, writes versus reads, method references, and discarded known non-void results |
| Project evidence | Explicit class imports, same-directory package peers, resolved `extends` and `implements` contracts |
| Third-party boundaries | Exact configured class or static-member imports; consumed raw results require a concrete conversion; outgoing objects mark their fields externally consumed |

For example, `import vendor.Api` is configured with
`"third_party_modules": ["vendor.Api"]`; a static import of `vendor.Api.fetch`
uses that full member name. Architecture patterns such as `vendor.*` match both.
Import wildcards are dependency evidence but are not expanded into semantic
bindings. Python's `imports.wildcard` rule is not applied to Java.

Locally declared or explicitly imported custom `Object` and collection names are
not mistaken for standard-library erasure. Bounded wildcards retain their bound.
Raw collection recognition is deliberately finite and does not infer arbitrary
user-defined generic declarations. Parameterized containers are still checked for
nested broad types. Java does not currently provide the dictionary-carrier
exceptions implemented for Python and JS/TS.

## Resolution limits

This is syntax-backed evidence, not javac type checking. Overload selection,
generic substitution, reflection, annotation processing, generated accessors,
wildcard/static-member project linking, fully qualified expression resolution,
and external classpaths are not compiler-resolved. Overloaded private methods are
conservatively retained; a mixed void/non-void overload family does not produce a
discarded-return warning. Override-family parameter matching remains name/slot
based and does not prove Java signature compatibility.

Public, protected and package-visible methods, annotated entry points and
constructors are retained as potential external contracts. Their explicit unused
parameters remain checked when a body exists. Implicit record fields/accessors
and compact-constructor parameters are not synthesized into semantic declarations.
Nested/anonymous class ownership, generated members and unresolved external
references retain the shared engine's inference limits. Keep compiler checks and
semantic review alongside this gate.

## Ownership and policy review

`languages/java/` owns grammar identity, metrics, imports, type interpretation and
semantic syntax. `plugins/builtins.py` composes its capabilities with the canonical
rules and API 2 profile. The shared inheritance contract now returns a concrete
tuple of original nodes to retain both `extends` and `implements`; no alternate
AST or erased carrier was added. Existing adapters wrap their former optional
inheritance node in that tuple.

Existing language-plugin ownership and object-model patterns cover the new files.
The repository import boundary additionally prohibits `tree_sitter_java` in shared
engines, matching the other grammar dependencies. No checker is disabled, no limit
is raised, and no source is excluded. The gate remains read-only.

## Regression evidence

`tests/test_java.py` covers discovery and CLI source preservation, recovered parse
warnings, all metric dimensions, type checks, suppression syntax, dependency and
dispatch checks, inheritance and explicit cross-file imports.
`tests/test_java_semantics.py` covers method references, overload uncertainty,
entry points, read-modify-write fields, lexical shadows and typed ingress.

Final validation on 2026-10-08:

| Command | Result |
| --- | --- |
| `uv run --no-sync code-harness --all` | Passed; 110 files, zero errors, 34 return-value warnings in unchanged files |
| `uv run --no-sync mypy src tests` | Passed; 109 source files |
| `uv run --no-sync ruff check src tests` | Passed |
| `uv run --no-sync ruff format --check src tests` | Passed; 110 files |
| `uv run --no-sync pytest -q` | 569 passed, including 60 Java regression cases |
| `git diff --check` | Passed |

Java adapter coverage was measured without adding a project dependency:

```sh
COVERAGE_FILE=/tmp/code-harness-java-coverage-final \
  uv run --no-sync --with coverage coverage run --branch \
  --source=code_harness.languages.java -m pytest -q \
  tests/test_java.py tests/test_java_semantics.py
COVERAGE_FILE=/tmp/code-harness-java-coverage-final \
  uv run --no-sync --with coverage coverage report -m
```

All Java production modules are new: 285/289 executable statements and 106/112
branches were covered (98% combined, rounded). Missing lines cover absent-parameter
and malformed-import guards, plus detached/missing method-node fallbacks; partial
branches include malformed imports and alternate generic-parameter traversal.
Those defensive paths remain reviewed but unexercised. Shared composition and
inheritance changes are exercised by the full regression suite; the numerical
coverage measurement above is limited to the new Java modules.
