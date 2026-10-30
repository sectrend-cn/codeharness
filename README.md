# Code Harness

A read-only engineering policy gate for Python, Go, Java, JavaScript/JSX and
TypeScript/TSX. No run mode modifies, stashes, stages, restores, deletes or
rewrites source files, and no run mode changes Git configuration. The shared
policy is in [Engineering standards](docs/engineering-standards.md).

## Run

Python 3.12 or newer is required. Run from this checkout, then activate the created environment:

```sh
python -m pip install --no-cache-dir uv==0.8.22
uv sync --locked --group dev
. .venv/bin/activate
```

The repository development checks are listed in `AGENTS.md` and run in
[the engineering workflow](.github/workflows/engineering.yml).

Run from any directory:

```sh
code-harness --root /path/to/project --all
code-harness --root /path/to/project --base BASE_COMMIT --format json
code-harness --root /path/to/project --staged
```

`--all` reads all selected working files including Git-ignored ones. `--base`
compares a commit to the working tree including untracked sources. `--staged`
reads changed index blobs and the index policy, never unstaged contents. Git
modes require the repository root.

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
target policy or development tools. The mount is read-only, and the calling
user's UID/GID preserve Git ownership checks. `--base` and `--staged` need the
complete Git metadata mounted too.

## Policy

Every target repository owns and commits its `.codeharness/code-harness.json`
policy. Copy [the example policy](examples/.codeharness/code-harness.json) to that
path and adapt it; paths inside the policy are relative to the repository root.

`include` and `exclude` control global file selection. All checkers are enabled by
default, so specify `enabled` only when disabling one.

Exit codes: **0** pass or warnings only for the reported scope, **1** error
findings, **2** configuration, encoding, filesystem or Git failure.

Repeated conditional field copies are checked in every supported language through
[`structure.guarded_projection`](.agents/skills/code-harness/references/checkers/structure.guarded_projection.md);
it defaults to three distinct destination fields in one local cluster.

See [Checker configuration](docs/checker-configuration.md) for all options,
defaults, language coverage and third-party usage boundaries.

## Language and rule plugins

All languages share one tree-sitter context. Language plugins own identity,
suffixes and grammar interpretation; application composition owns required
coverage and rule selection. Rules implement `RuleBundle`, consume
`TreeContext` and declare `RuleRequirements`. See
[Plugin architecture](docs/plugin-architecture.md), with per-checker Java scope
and limits covered by [checker configuration](docs/checker-configuration.md).

## Integration

Agent review rules can own review guidelines and invoke a configured ACP agent.
Findings are submitted incrementally through registered MCP tools, with explicit
completion and small acknowledgements. See [Agent review](docs/agent-review.md).

Any CI system that can run this image integrates with the same commands, and this
repository runs the same engineering checks in GitHub Actions; see
[the engineering workflow](.github/workflows/engineering.yml).

To run the gate image in a container, see the [Run section](#run) above.

A pre-commit hook may run `uv run --no-sync code-harness --staged` after the policy
is committed. Install hooks explicitly; this tool never changes Git configuration.

## Documentation

[Engineering standards](docs/engineering-standards.md) is the shared policy.
For installation, configuration, daily runs, finding triage and per-task gating,
start with [Getting started](docs/getting-started.md).
