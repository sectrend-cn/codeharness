# Code Harness

A read-only engineering policy gate for Python, Go, Java, JavaScript/JSX and
TypeScript/TSX. The shared policy is in [Engineering standards](docs/engineering-standards.md).

For installation, configuration, daily runs and finding triage, start with
[Getting started](docs/getting-started.md).

## Run

Python 3.12 or newer is required. Local development, Docker builds and GitHub
Actions install `uv` 0.8.22 and resolve dependencies from the official Python
Package Index (PyPI). The project configures no package mirror, and `uv.lock`
records the official PyPI artifact URLs. Install the locked environment:

```sh
python -m pip install --no-cache-dir uv==0.8.22
uv sync --locked --group dev
uv run --no-sync code-harness --all
uv run --no-sync pytest -q
uv run --no-sync mypy src tests
uv run --no-sync ruff check src tests
uv run --no-sync ruff format --check src tests
```

Every target repository owns and commits its `.codeharness/code-harness.json` policy.
Copy [the example policy](examples/.codeharness/code-harness.json) to that path in
your repository, then adapt its source paths, owners and import boundaries.
Paths inside the policy remain relative to the repository root. Run from any directory:

```sh
code-harness --root /path/to/project --all
code-harness --root /path/to/project --base BASE_COMMIT --format json
code-harness --root /path/to/project --staged
```

`--all` reads all selected working files, including files ignored by Git.
`--base` compares a commit to the working tree and includes untracked sources.
`--staged` reads changed index blobs and the index policy, never unstaged contents.
Changed modes report **affected definitions and module statements**: edits expand
to complete enclosing functions (including decorators), class-header edits expand
to the class, and edits to module statements expand to those statements. Pure
deletions retain a nearby line anchor. Untracked files receive a full audit.
Whole snapshots remain available for parsing and semantic evidence. Ownership and
source-placement checks apply to every changed file. `--all` still exposes all
historical debt. Deleted files have no current source to check. Git modes require
the repository root. Reports disclose the diagnostic scope in `scope`.

Exit codes: **0** pass or warnings only for the reported scope, **1** error findings, **2** configuration,
encoding, filesystem or Git failure. An empty full audit is an error. An empty
change audit reports zero files. Invalid syntax produces a warning on stderr,
not a defect, and checks continue on the recovered tree. Warnings disclose that
results may be inaccurate. All languages use tree-sitter; checks run on available
syntax evidence, and analyses requiring an unrecovered tree may be unavailable. Warnings alone return
0, including with JSON output. Parser infrastructure failures remain errors.
`syntax.invalid` is no longer a checker; remove it from existing policies.
No mode fixes, stashes, stages, restores, deletes or rewrites source files.

## Policy

Repeated guarded field copies are checked in every supported language through
[`structure.guarded_projection`](docs/guarded-projection.md). It defaults to three
distinct destination fields in one local cluster, including conditional object or
dictionary spreads where supported, independently of function complexity.

`include` and `exclude` select files for every checker. Each entry under
`checkers` configures one logical checker. Function metrics share the
`function_size` checker; other keys match their diagnostic IDs. All checkers are
enabled by default, so specify `enabled` only when disabling one:

```json
{
  "version": 2,
  "include": ["src/*", "tests/*"],
  "exclude": [],
  "checkers": {
    "function_size": {"lines": 50, "statements": 50, "complexity": 10, "nesting": 3, "parameters": 5},
    "architecture.owner": {
      "owners": [
        {"name": "domain", "paths": ["src/domain/*"]},
        {"name": "adapters", "paths": ["src/adapters/*"]},
        {"name": "tests", "paths": ["tests/*"]}
      ]
    },
    "architecture.import": {
      "boundaries": [{
        "name": "domain does not depend on adapters",
        "sources": ["src/domain/*"],
        "forbidden_imports": ["adapters", "adapters.*", "src.adapters", "src.adapters.*"]
      }]
    },
    "architecture.object_model": {
      "paths": ["src/domain/rules/*"]
    }
  }
}
```

To disable only public module-function checking, set:

```json
"architecture.object_model": {"enabled": false, "paths": ["src/domain/rules/*"]}
```

This leaves `architecture.dispatch` and every other checker unchanged. Omitted
checkers and omitted options use defaults. Text and JSON reports list configured
disabled checkers; JSON exposes `disabled_checkers` alongside `findings`; each finding has a
`severity`, and `usage_files` records the usage-reference scope.
The [repository policy](.codeharness/code-harness.json) shows function limits and project
architecture settings; default-only checkers are omitted and remain enabled.
`"function_size": {"enabled": false}` disables all five function metric checks.
See [Checker configuration](docs/checker-configuration.md) for all options,
migration from version 1, and parser prerequisites.

Patterns use case-sensitive shell matching; `*` spans slashes. Paths are relative
to the source root and use `/`. Define module-name patterns for Python/Go and
module specifier or normalized relative path patterns for JS/TS. Python relative
imports are normalized using their source directory. JS/TS relative imports also
match root-relative paths, with and without source extensions. Include both a
package itself and its descendants where needed. Type-only imports, re-exports,
literal `require()` and literal `import()` are checked. Java imports use qualified
type/member names, including static imports and wildcard suffixes. See
[Java support and limits](docs/java-support.md).

When `architecture.owner` is enabled and owners are configured, every selected
file must match exactly one. With no
owners or boundaries those architecture checks have no project-specific facts to
enforce. Configuration rejects unknown keys and wrong types. Review scope,
ownership, boundaries and limits as code; an empty or weakened policy is not proof
of architecture compliance. A staged policy change requires a separate full audit
and policy review before the staged gate can pass.

Environment directories (`.git`, `.venv`, `venv`, `node_modules`, `__pycache__`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`) are omitted. Authored tests, scripts
and fixtures have no blanket exemption. Generated/vendor exclusions, if necessary,
must be explicit in `exclude` and reviewed. Symlink traversal and invalid UTF-8
are errors. The full audit does not honor `.gitignore` as an architecture waiver.

## Enforcement and limits

The gate implements function size/complexity/nesting/parameter checks, common
explicit type erasure and assertion markers, Python interface annotations and
wildcard imports, prohibited checker suppression comments, ownership and declared
import boundaries. It also reports unused parameters, functions and unread fields, and
warns when known return values are discarded. Write-only fields count as unused;
objects passed to configured third-party libraries count as consumed.

Every supported language — Python, Go, Java and the JavaScript family — can use a
[standalone next-line diagnostic suppression](docs/comment-suppressions.md) with an
exact rule ID for an exception that received explicit (human) approval beforehand;
the approval precedes and is independent of the reason. The marker is the
language's own line comment: `#` in Python, `//` in Go, Java and the JavaScript
family. Malformed and unused directives remain errors.

Set `third_party_modules` to exact library import specifiers to enable directional
dictionary exceptions. Library inputs and callback returns may use erased
dictionaries; library outputs and callback inputs must become typed objects at
ingress. See [boundary and usage configuration](docs/checker-configuration.md#third-party-boundaries-and-usage)
for examples, callback handling, source scope and resolution limits.

It does not infer types, resolve package aliases or dynamic imports, prove runtime
ownership, detect all unused code, prove logging safety, or measure coverage.
JavaScript type safety requires a configured type-aware checker. Keep language
formatters, type checkers, tests, branch coverage and semantic architecture review
as separate required checks. A syntax-gate pass does not certify all policy rules.

## Language and rule plugins

The [decoupled architecture](docs/language-rule-decoupling.md) separates language
grammar adapters from rule registration using one tree-sitter context and typed
capabilities. Language plugins own identity, suffixes and grammar interpretation;
application composition owns required coverage and rule selection.

API 2 rules implement `RuleBundle`, consume `TreeContext` and declare
`RuleRequirements`. `LanguageRegistry` owns discovery; `AnalyzerRegistry` validates
composed analyzers and connects their session capabilities. Extend the concrete
analyzers from `builtin_analyzers()` or use `builtin_registry()` for the standard
composition. Each analysis session owns exact snapshot trees and semantic evidence.
Explicit in-process registration is supported; package discovery is not implemented.

`architecture.dispatch` rejects recognized language/rule identity switches.
Set `checkers["architecture.object_model"].paths` to extension-module path patterns to enforce class-owned
entry points with `architecture.object_model`. This repository enables those
checks for its own analyzers and rules. See [Plugin architecture](docs/plugin-architecture.md)
for extension examples, ownership, compatibility changes, and detection limits.

Agent review rules can own review guidelines and invoke a configured ACP agent.
Findings are submitted incrementally through registered MCP tools, with explicit
completion and small acknowledgements. See [Agent review](docs/agent-review.md).

## Integration

Build the image from this checkout:

```sh
docker build -t code-harness:0.1.0 .
```

Run a one-line full audit from a target repository containing
`.codeharness/code-harness.json`:

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/workspace:ro" code-harness:0.1.0 code-harness --all
```

The image installs the locked runtime dependencies and Git. It does not contain a
target policy or development tools. The mount is read-only; the calling user's
UID/GID preserves Git ownership checks for `--base` and `--staged`. For those modes,
mount the complete Git metadata too; linked worktrees need their external Git
metadata available at the same paths. ACP review additionally needs its configured
agent executable and credentials; those are not bundled.

Any CI system that can run this image integrates with the same commands.

This repository runs the same six checks in GitHub Actions. The
[engineering workflow](.github/workflows/engineering.yml) installs uv and the
locked development environment, then runs the full audit, type checks, lint,
formatting check and tests. [CI workflow](.github/workflows/ci.yml) calls it for
every branch push and pull request, and the
[release workflow](.github/workflows/release.yml) calls it before building a
release. All jobs use GitHub-hosted `ubuntu-latest` runners, so no self-hosted
runner tag is needed.

A pre-commit hook may run `uv run --no-sync code-harness --staged` after the policy
is committed. Install hooks explicitly; this tool never changes Git configuration.
Bootstrap and policy amendments need `--all` plus review. Historical debt is
reported and tracked; do not introduce suppressions to make adoption appear green.

## Python package releases

The package version is dynamic. [hatch-vcs](https://github.com/ofek/hatch-vcs)
derives it from the Git tag of the checkout, so no release edits `pyproject.toml`
or `uv.lock`. Pushing a `v`-prefixed tag runs
[the release workflow](.github/workflows/release.yml), which additionally requires
the tag to match `^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z][0-9A-Za-z.-]*)?$`. Tags
such as `v1.2.3` and `v1.2.3-rc.1` are therefore release tags, while `1.2.3` is
not published by CI. Distribution filenames normalize the version, so
`v1.2.3-rc.1` becomes `1.2.3rc1`.

The tag is the only version source: the release workflow does not set
`SETUPTOOLS_SCM_PRETEND_VERSION`. It checks out the full history and tags
(`fetch-depth: 0`), because a full clone is the most reliable way to derive the
version from the tag: a shallow clone of a tag event usually carries the
triggering tag, but depending on that is fragile, and a history without any tag
yields a development version such as `0.0.0.dev32+g602770ea0.d20261028`
rather than the release version. After the engineering checks it builds a
source distribution and wheel with `uv build --no-sources`, then compares the
version in the artifact file names with the tag as PEP 440 versions; a mismatch
fails the run before anything is published. The build installs the wheel into a
runtime-only environment and starts `code-harness --help` as a smoke test, and
passes `dist/` to the publish job.

The publish job is the only job that requests `contents: write`. It uploads the
built files to the GitHub Release of the tag with the workflow's default
`GITHUB_TOKEN`. Neither `uv publish` nor a package index credential is involved,
and each release keeps the `.tar.gz` and `.whl` as assets. Every other job runs
with read-only permissions.

Without a CI override, local builds derive their version from Git. Source copies
without Git metadata fall back to `0.0.0.dev0`. To build a specific version locally:

```sh
SETUPTOOLS_SCM_PRETEND_VERSION=1.2.3 uv build --no-sources
```

GitHub Releases is not a package index, so installation names the release asset
explicitly and dependencies are still resolved from PyPI:

```sh
uv tool install https://github.com/sectrend-cn/codeharness/releases/download/v1.2.3/code_harness-1.2.3-py3-none-any.whl
```

Replace `sectrend-cn/codeharness` with the repository that published the release
when installing from a fork.

To use a local checkout across projects, install an editable tool environment:

```sh
uv tool install --editable /absolute/path/to/code-harness
code-harness --root /absolute/path/to/consumer-project --all
```

If uv already manages a released `code-harness` tool, add `--force` to replace that
installation. Keep the checkout at the same path: source edits take effect without
reinstallation. Re-run the install command after changing dependencies or package
metadata. An active project's virtual environment can shadow the user-level
command; use `~/.local/bin/code-harness` explicitly when needed.
