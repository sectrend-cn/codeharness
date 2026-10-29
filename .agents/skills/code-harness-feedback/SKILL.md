---
name: code-harness-feedback
description: Report suspected code-harness false positives to the project issue tracker. Use when a local code-harness scan produces widespread findings the user believes are wrong (false positive, misreport, suspected checker defect), when you must prepare a minimal reproducible snippet and a ready-to-paste GitHub issue (diagnostic ID, install method and version, OS, full command line, policy, reproduction, scale statistics, reasoning), or when you must guide submission through the GitHub CLI or a manual paste; also covers recommending one approved next-line suppression comment instead of an issue for one-off cases that do not generalize.
---

# Reporting code-harness false positives

code-harness is a read-only, parse-based architecture policy gate. When its
findings look wrong, the defect belongs upstream in the checker, not in the
scanned project: this skill turns a suspicion into evidence, decides whether it
generalizes, builds a minimal reproduction, and prepares a GitHub issue for the
project repository (https://github.com/sectrend-cn/codeharness).

## When to use this skill

- A local code-harness run (task gate or full audit) reports many findings that
  the user believes are wrong.
- The user suspects a specific diagnostic ID misreports a common construct.
- The user wants a reproducible snippet or an issue draft for a code-harness
  false positive.

Not for: policy changes (thresholds, excludes, owners, boundaries, enable
flags). Those are architecture decisions with their own audit and review
process, and they are never a way to make a report disappear.

## Ground rules

1. Treat the scanned project as read-only. Collect evidence by re-running the
   gate, never by editing the project's sources or policy to change the result.
2. One issue carries exactly one diagnostic ID — the `rule` value printed by the
   gate. Two rules mean two issues.
3. Never add suppressions, lower limits or disable checkers to silence the
   report. An approved suppression answers an approved exception, not a possible
   checker defect.
4. Never submit an issue without explicit user consent. You prepare the text and
   the commands; the user decides whether the issue is filed.
5. Report only behavior you actually observed. If something is unknown (for
   example the installed version), say so instead of guessing.

## Step 1 — Collect evidence (read-only)

Record the exact command line the user ran, including the mode and every option,
and the exit code. To get structured data, rerun the gate read-only:

```sh
code-harness --all --format json
```

Use `--root` when the scanned project is not the current directory, and
`--config` when its policy is not at the default
`.codeharness/code-harness.json` (resolved relative to the root):

```sh
code-harness --root <project root> --config <policy path> --all --format json
```

From the JSON report take, for every finding, the `rule` (the diagnostic ID), the
`path`, `line`, `column`, `message` and `severity`. Group the findings by `rule`
and continue with the one diagnostic ID the user is complaining about. For that
single ID count the finding total N and the number of distinct files M, and keep
a short list of sample paths.

The text format is for reading. Each finding is one line of
`path:line:column: rule: message`; for a warning the `warning: ` prefix sits
between the position and the rule, so the line reads
`path:line:column: warning: rule: message`. After the findings and before the
final summary line the run prints `Diagnostic scope: <scope>.`, then a
`Usage reference scope: <N> files.` line when usage evidence was collected, then
a `Disabled checkers: <ids>` line when the policy disables checkers. The run
ends with a summary line such as `Architecture all: 12 files; 3 findings.`.
Exit codes: `0` no error-severity findings, `1` error-severity findings present,
`2` configuration, filesystem, encoding or Git failure.

Also collect the environment facts the issue needs:

- how code-harness was installed (for example a release wheel whose URL contains
  the version, a `uv tool` install, a `pip` install, or a source checkout);
- the version that installation exposes — `uv tool list`,
  `python -m pip show code-harness`, or `git describe --tags` inside the
  checkout. The CLI has no version flag, so the version can only come from the
  installation itself; when those commands print nothing, record that the
  version is unavailable;
- the operating system and the language/runtime of the scanned sources.

## Step 2 — Triage universality

Try to reduce the finding to one minimal self-contained snippet, then ask: is
this construct common, and would another project hit it too?

**No universality** — a project-specific pattern, an intentional exception, a
single odd file. Do not file an issue. Recommend an approved next-line
suppression comment instead, using the language's own line-comment marker:

```python
# code-harness: ignore-next-line type.annotation -- Legacy adapter boundary.
value: object = read_payload()
```

```go
// code-harness: ignore-next-line type.broad -- Generated wire payload.
type Payload any
```

The same `//` form is available in Java, JavaScript, JSX, TypeScript and TSX.
The directive is a standalone comment on the physical line immediately before
the finding, naming one exact diagnostic ID and followed by `-- ` and a nonblank
reason. The complete syntax and validation rules live in
`docs/comment-suppressions.md` in the code-harness source checkout.

State these constraints when you recommend it:

- the exception must have been approved by a human beforehand; the reason only
  records that approval and is not proof of safety;
- metric findings are suppressed by their metric ID (for example `size.lines`),
  not by the checker key;
- block comments, wildcards, lists, a missing reason and a directive with no
  matching finding are all invalid and are themselves reported as
  `type.suppression`;
- `type.suppression` cannot suppress itself.

**Suspected generalizable checker defect** — several independent locations, or a
common construct reported wrongly. Continue with step 3.

## Step 3 — Build a minimal reproduction

Build the reproduction in a system temporary directory, isolated from the
scanned project, and never modify the scanned project to produce it.

```sh
mkdir -p <repro>/.codeharness
```

Layout:

```
<repro>/
  .codeharness/code-harness.json
  sample.py
```

The policy file is mandatory: a missing policy makes the run fail with exit
code 2. The minimal valid policy is an empty object, and it is enough unless the
false positive depends on checker options — in that case include only the
options that matter:

```json
{}
```

Add the smallest source file that still triggers the rule, then run:

```sh
code-harness --root <repro> --all --format json
```

The `--all` mode reads the files on disk and needs no Git repository, which is
why the temporary directory works. Confirm that the same `rule` still appears
and keep the exact output. If the finding disappears, the report is not
reproducible in isolation: say so and do not file an issue. Delete the
temporary directory once the issue text is written.

## Step 4 — Compose the issue

Write the issue body to a file in the workspace, named for the diagnostic ID
(for example `code-harness-false-positive-type.broad.md`), report its actual
path, and show the same body in a fenced block so the user can copy it. Fill
every field from observations made in steps 1 to 3.

````markdown
## Diagnostic

- Diagnostic ID: `<rule>` (the `rule` field of the report)
- Language / analyzer: <language>
- Severity: <error or warning>

## Environment

- Installation: <how code-harness was installed>
- Version: <version visible from that installation, or "unknown">
- OS: <operating system and version>
- Scanned source language / runtime: <language and runtime version>

## Command line

```sh
code-harness --root <root> --config <policy-path> --all --format text
```

## Policy (`.codeharness/code-harness.json`)

```json
{}
```

## Minimal reproduction

Layout:

```
<repro>/
  .codeharness/code-harness.json
  sample.py
```

Policy `.codeharness/code-harness.json`:

```json
{}
```

`sample.py`:

```python
def add(left, right):
    return left + right
```

Command:

```sh
code-harness --root <repro> --all --format text
```

Expected behavior: <what the correct result is — for a false positive that
usually means no finding is reported here — and why>

Actual output:

```
<paste the full text output of the reproduction run, line for line>
```

## Scale in the original project

- Findings for this diagnostic ID: <N>
- Files involved: <M>
- Sample paths: <path>, <path>, <path>

## Why this looks like a false positive

<the code semantics, what the checker appears to assume, and where the two
diverge>

## Workarounds tried (optional)

<what was attempted and why it is not an acceptable resolution>
````

Replace the example file names and code with the real reproduction. Keep the
actual output verbatim — do not paraphrase or trim lines that change its
meaning.

The repository also provides the same fields as a GitHub issue template: the
new-issue page at https://github.com/sectrend-cn/codeharness/issues/new offers a
`False positive report` template, and opening it pre-fills the suggested title
and the same `## ` fields, which is a convenient start for the manual path in
step 5. That repository template plays no part in the CLI path: the
`gh issue create --body-file` command sends the body file prepared here
verbatim.

## Step 5 — Guide the submission

The submission decision belongs to the user. Present both paths, then wait.

**Path A — GitHub CLI.** Check that the CLI is authenticated:

```sh
gh auth status
```

If it is available and the user explicitly agrees, create the issue from the
file you wrote:

```sh
gh issue create --repo sectrend-cn/codeharness --title "<title>" --body-file "<body file>"
```

Suggested title: `False positive: <rule> (<language>)`. Report the issue URL that
the command prints. If `gh` is missing or unauthenticated, and the user declines,
use path B.

**Path B — manual paste.** Open https://github.com/sectrend-cn/codeharness/issues/new
and paste the title and the body from the file or the fenced block above.

Rules for both paths:

- Do not submit, and do not click for the user, without their explicit consent.
- Do not attach secrets, credentials or unrelated proprietary source; the
  reproduction should be the minimal snippet only.
- Do not batch-add suppressions or edit the scanned project's policy to make the
  report disappear while waiting for a fix.
