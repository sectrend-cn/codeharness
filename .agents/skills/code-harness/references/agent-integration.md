# Agent integration notes — code-harness skill

How a consuming repository connects an agent to this skill, and the limits
that apply. File anchors in these notes refer to your code-harness source
checkout (the same checkout the skill directory was copied from); no network
location is assumed.

## Generic statement (any agent)

This skill is a plain directory with a `SKILL.md` in Agent Skills format. Any
agent that implements the Agent Skills directory convention can discover it
under `.agents/skills/` (project level, found from the working directory up
through its ancestors) or `~/.agents/skills/` (user level). Any agent that can
read files and run shell commands can also use it without a discovery
mechanism: read `.agents/skills/code-harness/SKILL.md` from the consuming
repository and follow it, for example through the AGENTS.md pointer snippet in
SKILL.md. Nothing here promises that a specific tool will discover or load the
skill on its own; the concrete integration steps are up to each agent.

## Adapting agent-specific skill directories

Some agents load skills only from their own directory. Where that directory
lives decides the form:

- Outside the audited repository root (`--root`), for example a user-level or
  agent-specific skills directory, a symlink keeps a single source of truth:

```sh
ln -s /absolute/path/to/repo/.agents/skills/code-harness <agent-skills-dir>/code-harness
```

- Inside the repository root, copy the directory instead; never adapt with a
  directory symlink there. The full audit `--all` refuses to traverse any
  directory symlink under the root and exits 2, and the refusal happens
  during enumeration, before include/exclude filtering — no exclude pattern
  bypasses it. The Git-based modes do not enumerate the disk, which hides the
  damage: on an unchanged tree `code-harness --base HEAD` still exits 0 with
  a 0-files report while every full audit (bootstrap, policy re-review, and
  the D12 fallback row) is permanently broken; a `--base` run with changed
  files exits 2 as soon as usage evidence is read from disk. Treat the copy
  as a drifting duplicate: re-copy after every update of the source,
  otherwise the two locations diverge silently. Windows systems without
  usable symlinks use the copy form everywhere.

## Team / CI usage

Out of scope for this skill; see the
[Integration section](../../../../README.md#integration) of the README in your
code-harness source checkout.
