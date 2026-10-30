# Engineering policy

Read `docs/engineering-standards.md` before changing or reviewing authored code.
It defines shared style, type preservation, ownership, dependency direction,
function limits and semantic review obligations for Python, Go, Java and JavaScript/TypeScript.

Agent sessions should read `.agents/skills/code-harness/SKILL.md` before gate tasks.

- Preserve concrete types across production code, tests, helpers and scripts.
  No broad carriers, casts or serialization round trips to bypass type checking.
- Reuse canonical domain contracts and keep validation with their owner.
- Keep ownership and dependency rules in `.codeharness/code-harness.json` consistent with the
  implementation. Policy changes require a full audit and architecture review.
- Run `uv run --no-sync code-harness --all`, `uv run --no-sync mypy src tests`,
  `uv run --no-sync ruff check src tests`, `uv run --no-sync ruff format --check src tests`
  and `uv run --no-sync pytest -q` before completing gate changes.
- Do not automatically roll back, revert, discard, reset, restore, overwrite or
  delete code changes. Preserve current state and obtain explicit user authority
  before any reversal. Gate execution must remain read-only.
- Do not add implementation comments or suppression comments. Use meaningful
  docstrings, architecture documentation and behavioral tests for rationale.
