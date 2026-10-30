# code-harness getting started

This guide is for individual developers using code-harness. It covers obtaining and installing the
tool, configuring a policy for a target repository, day-to-day runs, triaging existing findings, and
the continuous gate scenario of running the gate at the end of every code task.

code-harness is a read-only, analysis-driven engineering policy gate: no run mode modifies, stages,
restores, deletes or rewrites source files, and none of them changes Git configuration.

A Chinese translation of this page is available at
[zh/getting-started.md](zh/getting-started.md).

## Installation

### Prerequisites

- Python 3.12 or later.
- Using `uv` to manage a dedicated tool environment is recommended; for obtaining `uv` itself and
  for the repository development commands, see
  [the Run section of the README](../README.md#run).

### Obtaining the source

Obtain a source checkout of code-harness (clone the repository, or unpack the source archive you
received). Throughout this page `/path/to/code-harness` refers to that checkout directory. The
checkout holds the tool's source, the sample policies under `examples/`, and the
`.agents/skills/code-harness/` skill.

### Local installation

Install the command line from that checkout directory:

```sh
uv tool install /path/to/code-harness
```

Without uv, the pip equivalent is:

```sh
python -m pip install /path/to/code-harness
```

The installation places `code-harness` in the user-level executable directory (for example
`~/.local/bin`), so make sure that directory is on your `PATH`. If a uv tool installation of the same
name already exists and you need to replace it, pass `--force` to `uv tool install`.

### Verification

```sh
code-harness --help
code-harness --root /path/to/project --all
```

The first confirms the command works and lists the options actually supported: `--root` (default
`.`), `--config` (default `.codeharness/code-harness.json`), `--format` (`text` or `json`), and the
required, mutually exclusive `--all` / `--staged` / `--base`. The second runs a full audit against
the target repository; if the target repository has no policy yet as described in
[Configuration](#configuration), that command reports that no policy file was found and exits 2,
which is expected behaviour — finish the configuration first and then come back to verify.

### Container usage

To run in a container with the target repository mounted read-only, see
[the Integration section of the README](../README.md#integration).

### Obtaining the skill

The skill that agents use comes from the same source checkout: copy `.agents/skills/code-harness/`
from the checkout to the consuming project's skill location. See
[Agent integration](#agent-integration) for the integration paths.

## Configuration

### Establishing a repository policy

Every target repository holds and commits its own `.codeharness/code-harness.json` (the policy path
resolves relative to `--root`, in Git modes as well). The tool has no command that generates or
initialises a policy; the file is written and committed by hand: the only options the tool itself
defines are `--all`, `--staged`, `--base`, `--root`, `--config` and `--format`, plus the
automatically provided `-h, --help` help option.

There are two ways to start. You can copy the
[sample policy](../examples/.codeharness/code-harness.json) to `.codeharness/code-harness.json` in
the target repository and then adapt it to that repository's structure; or you can write a minimal
working policy by hand, in which an empty `checkers` object (or omitting that key) keeps every
checker enabled by default:

```json
{"version": 2, "include": ["src/*"], "exclude": [], "checkers": {}}
```

What you can add to the policy as needed:

- `include` / `exclude`: decide which files take part in all checks; case-sensitive, `*` may span
  `/`, paths resolve relative to the repository root.
- `owners` under `architecture.owner`: declare a single accountable owner for each selected file.
- `boundaries` under `architecture.import`: declare forbidden dependency directions.
- `function_size`: limits on function lines, statements, complexity, nesting and parameters.

When you start from a minimal policy, build it up in the order below and take a reading at each step
before deciding the next one:

1. Use `include` / `exclude` to delimit the files that take part in the audit;
2. Run `code-harness --all` for the first time to get a baseline reading — an existing repository
   usually exits 1, which is expected, see
   [First full audit of an existing repository](#first-full-audit-of-an-existing-repository); if no
   supported source file falls inside the range, it exits 2 as a configuration error, so `include`
   must be fixed first;
3. Add `owners` under `architecture.owner` for the selected files;
4. Declare `boundaries` under `architecture.import`;
5. Adjust the `function_size` thresholds to what the repository actually needs, or add the
   `encoding` declaration under `type.broad`.

Each step above may change the policy: threshold, exclusion and owner/boundary adjustments get their
own full audit and review under the discipline in the next section, and are not a means of clearing
existing findings.

### Discipline for changing the policy

A policy change (adjusting thresholds, adding exclusions, changing owners/boundaries) is an
architecture decision, not a way to make findings disappear. The first bootstrap version and every
revision each need a separate full audit with `--all` and a review. As soon as `--staged` sees a
policy change in the index it refuses with exit 2, until the full audit passes and the change is
committed.

See [Checker configuration](checker-configuration.md) for all options, the policy structure,
per-language coverage and implementation limits.

## Running

Exactly one of the three modes must be given; `--all` / `--staged` / `--base <commit>` are mutually
exclusive:

- `--all`: audits every work-tree file selected by the policy, **including** Git-ignored files; it
  exposes all existing debt.
- `--base <commit>`: compares the given commit with the work tree, **including** untracked new files
  (new files are audited in full).
- `--staged`: reads only the blobs in the index and the policy in the index; it cannot see unstaged
  content.

Canonical commands:

```sh
code-harness --all
code-harness --staged
code-harness --base <commit>
code-harness --root /path/to/project --all
code-harness --all --format json
```

`--root` defaults to the current directory and must be the repository root in Git modes;
`--config` defaults to `.codeharness/code-harness.json`; the two combine as
`code-harness --root /path/to/project --config .codeharness/code-harness.json --all`.

Exit codes:

| Exit code | Meaning |
|---|---|
| `0` | No error-level finding (warnings do not matter) |
| `1` | At least one error-level finding |
| `2` | Configuration, encoding, file-system or Git failure (including a policy change under staged, until a separate `--all` full audit passes and is committed) |

The change modes (`--base` / `--staged`) resolve the snapshot in full but report the **affected
definitions and module statements**: an edit inside a function expands to the whole function
(decorators and signature included), a class-header edit selects the whole class, a module-statement
edit selects that statement; a pure deletion keeps a nearby line anchor; untracked files are audited
in full. Ownership and placement constraints still apply to every changed file. Reports use `scope`
to distinguish `full_files` from `affected_definitions_and_statements`.

Other semantics: an empty full audit counts as a configuration error (exit 2); an empty change audit
reports 0 files; syntax errors only produce a warning on stderr without changing the exit code, and
the remaining checks continue on the recovered syntax tree, so their results may be inaccurate;
warnings do not affect exit 0.

`--format json` emits the current report structure: `scope`, `findings` (each with a `severity`),
`usage_files`, `disabled_checkers`, plus the mode and the file counts. That structure is delivered as
currently implemented and is not promised as a stable external ABI; on upgrade, go by the actual
output.

Every mode is read-only throughout: no fixing, stash, stage, restore, deletion or rewriting of source
files.

## Triage

### The three disposition paths

1. **Fix first**: a finding is evidence of a policy violation, so the default action is to change the
   code.
2. **Line suppression (every supported language)**: Python, Go, Java and the JavaScript family all
   allow a next-line suppression comment for one exact rule id, using that language's own line-comment
   marker — `#` for Python, `//` for Go, Java and the JavaScript family; but the mechanism may only be
   used for exceptions with **explicit (human) approval obtained in advance** — approval comes before
   and independently of the reason, the reason only records that approval and is not a proof of
   safety, and the exception must be reconsidered when how the code is used changes. Block-comment
   forms, wildcards, lists, `type.suppression` itself and a missing reason all report a
   `type.suppression` error; abusing suppression is itself an error. See
   [Approved next-line diagnostic exceptions](comment-suppressions.md) for the syntax and validation
   rules.
3. **Policy revision**: threshold, exclusion or owner adjustments are policy changes and need their
   own `--all` full audit and review; they must not be used to manufacture a green result.

### Debt semantics

`--all` exposes all existing debt while `--base` reports only affected definitions and module
statements; the two readings cannot stand in for each other.

- `0`: no error-level finding in this run's range; warnings may be present.
- `1`: at least one error-level finding in this run's range; each one has to be dealt with.
- `2`: the gate cannot reach a conclusion (configuration, encoding, file-system or Git failure); fix
  the input first, then talk about whether it passes.

### First full audit of an existing repository

In a repository that already carries debt, the first `--all` after bootstrapping the initial policy
usually exits 1; that is the expected reading, not a gate failure:

1. Read the findings one by one and fix genuine violations first.
2. For rules that reflect genuine historical debt or no longer match the repository's current state,
   adjust the policy deliberately (thresholds, exclusions, owners), then re-run `--all` and review.
3. Record which findings were fixed, which were accepted through a policy change, and the review
   conclusion.

## Per-task gating

Run the gate once at the end of every code task, before reporting the task done, and report
the mode, exit code and findings truthfully, including the error and warning counts and the key
items; human development follows the same rules. The situation-to-command table (uncommitted
changes, commits produced by the task, unknown start commit, staged-audit boundary), the three
policy rules, the supporting self-checks and the report format are authoritative in the
[code-harness skill](../.agents/skills/code-harness/SKILL.md). Those self-checks include the
files-count check: the report's last line reads `Architecture base: N files`, and N=0 cannot
count as a pass when the task really changed code.

## Agent integration

The skill directory comes from `.agents/skills/code-harness/` in the source checkout (with
`SKILL.md` and `references/`). Three integration paths:

1. **Native skills directory**: when the consuming project follows the skills-directory convention,
   copy `.agents/skills/code-harness/` from the checkout to the project's (or the user-level) skills
   location, and the agent can route and load it by the skill description.
2. **Agent-specific directory adaptation**: when an agent reads instructions only from its own
   directory, the integration shape follows from where that directory lives. Inside a repository
   (within `--root`) **directory symlinks are not allowed**: before include/exclude filtering the
   gate refuses to traverse any directory symlink (exit 2), and `exclude` cannot get around it.
   Integration inside a repository is therefore primarily a **copy**, and copy drift is accepted
   (after the source is updated you have to copy again, otherwise the two copies diverge); symlinks
   are only for directories **outside** `--root` (such as a user-level skills directory), which is
   also where the single-source-of-truth benefit lies.
   Blast radius: while a directory symlink remains inside the repository, `--all` (the bootstrap
   first run, policy review, and the fallback when the start commit is unknown) and a `--base` with
   real changes (whose usage evidence also goes through whole-disk enumeration) both exit 2. The only
   shape that still passes silently is the 0-file degenerate one, that is, the false pass that
   supporting instruction 1 in Per-task gating already requires you to detect (when files=0 while the
   task really changed something, you must choose another base); `--staged` does not walk the disk,
   but it is not used for post-task gating. The real impact shows up at the first real task.
3. **AGENTS.md pointer snippet**: for an agent that uses `AGENTS.md` as its instruction entry point,
   add the snippet below to that instruction file. Integration is manual pasting and does not
   rewrite AGENTS.md (it is the user's own policy asset):

```markdown
<!-- code-harness skill pointer -->
When adopting, configuring, or running code-harness, or triaging its findings,
first read `.agents/skills/code-harness/SKILL.md` and follow it.
```

For the general integration paths and limits, see
[agent integration notes](../.agents/skills/code-harness/references/agent-integration.md).
