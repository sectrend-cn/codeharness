# Checker reference — code-harness skill

Index of the built-in checkers. The schema has 18 logical checkers, which produce
22 built-in diagnostic IDs; function metrics share one checker and every other
checker name matches its diagnostic ID. Each checker has its own page under
`checkers/`, holding what it reports, which analyzers register it, where its
behavior differs between languages, every option with its default and type, and
correct versus incorrect configuration examples.

Configuration lives in the target repository's `.codeharness/code-harness.json`,
or in the path selected with `--config`; it stays relative to the source root in
every mode. Every checker accepts `enabled`, a strict boolean defaulting to
`true`. There is no per-language and no per-file `enabled`. Unknown checker IDs
and unknown options are rejected, including when that checker is disabled, and
unknown options inside nested option objects are rejected the same way. Omitted
entries and omitted options keep their defaults, so `enabled: true` and
default-only entries are unnecessary. `include` and `exclude` are the only global
file selectors. Except for `unused.return`, which is always a warning, findings
are errors and fail the gate with exit code 1; warnings alone leave exit code 0.

Disabling a checker removes its diagnostics from every selected file. Text
reports list disabled checker names and JSON reports include a
`disabled_checkers` array; findings keep their diagnostic IDs, so disabling
`function_size` is reported by that name while its findings would have used the
five `size.*` IDs. Fully disabled bundles skip parsing, and a disabled checker
never permits broken plugin registration. Changing an enable flag is a policy
change subject to the same full audit and review as changing a threshold.

The equivalent facts appear in `docs/checker-configuration.md`, the maintenance
note kept with this repository for its own development, while
[comment suppressions](comment-suppressions.md) covers suppression directives in
depth. Keep this index, the checker pages and `docs/checker-configuration.md` in
the same batch when either side changes, and treat the implementation as the
final authority.

## Coverage

Six analyzers cover seven languages: Python (`.py`, `.pyi`), Go (`.go`), Java
(`.java`), JavaScript and JSX (`.js`, `.jsx`, `.mjs`, `.cjs`), TypeScript
(`.ts`, `.mts`, `.cts`) and TSX (`.tsx`).

Every analyzer registers the same base set of 17 diagnostic IDs:

- Usage: `unused.parameter`, `unused.function`, `unused.field`, `unused.return`.
- Boundaries and directives: `type.boundary`, `type.suppression`.
- Function metrics: `size.lines`, `size.statements`, `size.complexity`,
  `size.nesting` and `size.parameters`, all configured through the single
  `function_size` checker.
- Architecture: `architecture.owner`, `architecture.structure`,
  `architecture.import`, `architecture.dispatch`, `architecture.object_model`.
- Structure: `structure.guarded_projection`.

The remaining five diagnostic IDs are registered per language:

| Analyzer | Additional diagnostic IDs |
| --- | --- |
| Python | `type.annotation`, `type.signature`, `type.assertion`, `type.broad`, `imports.wildcard` |
| Go | `type.broad` |
| Java | `type.assertion`, `type.broad` |
| JavaScript and JSX | `type.broad` |
| TypeScript and TSX | `type.assertion`, `type.broad` |

A registered diagnostic reports only for the analyzer that registered it. For
example, `type.annotation`, `type.signature` and `imports.wildcard` appear in
Python files only, and `type.assertion` covers Python, Java, TypeScript and TSX
but not Go or JavaScript.

Registration is not the same as a reachable candidate. `architecture.object_model`
is registered everywhere, yet Java files cannot report it because Java has no
module-level functions; its page records the per-language candidate rules.

## Checker index

| Checker | Reports | Languages |
| --- | --- | --- |
| [`structure.guarded_projection`](checkers/structure.guarded_projection.md) | Repeated guarded field copies in one local region (three distinct destination fields by default) | All |
| [`function_size`](checkers/function_size.md) | Function lines, statements, complexity, nesting and parameters; one switch for `size.lines`, `size.statements`, `size.complexity`, `size.nesting` and `size.parameters` | All |
| [`type.annotation`](checkers/type.annotation.md) | Broad or bare Python annotations and invalid forward annotations | Python |
| [`type.signature`](checkers/type.signature.md) | Missing Python parameter and return annotations | Python |
| [`type.broad`](checkers/type.broad.md) | Recognized broad type markers and JSON serialization outside proven outputs and permitted library inputs | All; markers differ per language |
| [`type.boundary`](checkers/type.boundary.md) | Recognized library results and callback inputs used without typed conversion | All |
| [`unused.parameter`](checkers/unused.parameter.md) | Parameters without resolved read usage | All |
| [`unused.function`](checkers/unused.function.md) | Non-exported functions and methods without resolved references | All |
| [`unused.field`](checkers/unused.field.md) | Fields without reads; initialization and writes alone do not count | All |
| [`unused.return`](checkers/unused.return.md) | Known non-void results discarded at a call site; always a warning | All |
| [`type.assertion`](checkers/type.assertion.md) | Unchecked casts and assertions | Python, Java, TypeScript, TSX |
| [`type.suppression`](checkers/type.suppression.md) | Foreign suppression directives and malformed or unused next-line exceptions | All |
| [`imports.wildcard`](checkers/imports.wildcard.md) | Python wildcard imports | Python |
| [`architecture.owner`](checkers/architecture.owner.md) | Missing or overlapping responsibility owners | All |
| [`architecture.structure`](checkers/architecture.structure.md) | Selected modules outside their configured owning locations | All |
| [`architecture.import`](checkers/architecture.import.md) | Dependencies forbidden by configured boundaries | All |
| [`architecture.dispatch`](checkers/architecture.dispatch.md) | Language and rule identity comparison or match/switch dispatch | All |
| [`architecture.object_model`](checkers/architecture.object_model.md) | Non-underscore module-level functions in configured extension paths | Python, Go, JavaScript, TypeScript, TSX; not Java |

New checker pages start from [the checker page template](checkers/TEMPLATE.md),
which encodes the unified language format and the checklist for adding a checker.
`TEMPLATE.md` is the only non-checker file in that directory.
