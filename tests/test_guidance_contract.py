"""Verify user guidance against the shipped CLI, repository links and contract text."""

import re
import shlex
from pathlib import Path

import pytest

from code_harness.cli import _arguments

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
GUIDE_PATH = REPOSITORY_ROOT / "docs/getting-started.md"
README_PATH = REPOSITORY_ROOT / "README.md"
SKILL_PATH = REPOSITORY_ROOT / ".agents/skills/code-harness/SKILL.md"
AGENT_REFERENCE_PATH = SKILL_PATH.parent / "references/agent-integration.md"
AGENT_REFERENCE_LINK = "../.agents/skills/code-harness/references/agent-integration.md"
CHECKER_REFERENCE_PATH = SKILL_PATH.parent / "references/checkers.md"
CHECKER_REFERENCE_LINK = "references/checkers.md"
CHECKER_DOCUMENT_DIRECTORY = SKILL_PATH.parent / "references/checkers"

CHECKER_IDS = frozenset(
    {
        "architecture.dispatch",
        "architecture.import",
        "architecture.object_model",
        "architecture.owner",
        "architecture.structure",
        "function_size",
        "imports.wildcard",
        "structure.guarded_projection",
        "type.annotation",
        "type.assertion",
        "type.boundary",
        "type.broad",
        "type.signature",
        "type.suppression",
        "unused.field",
        "unused.function",
        "unused.parameter",
        "unused.return",
    }
)

DIAGNOSTIC_IDS = frozenset(
    {
        "architecture.dispatch",
        "architecture.import",
        "architecture.object_model",
        "architecture.owner",
        "architecture.structure",
        "imports.wildcard",
        "size.complexity",
        "size.lines",
        "size.nesting",
        "size.parameters",
        "size.statements",
        "structure.guarded_projection",
        "type.annotation",
        "type.assertion",
        "type.boundary",
        "type.broad",
        "type.signature",
        "type.suppression",
        "unused.field",
        "unused.function",
        "unused.parameter",
        "unused.return",
    }
)

SIZE_DIAGNOSTIC_IDS = frozenset(
    {
        "size.complexity",
        "size.lines",
        "size.nesting",
        "size.parameters",
        "size.statements",
    }
)

CHECKER_DOCUMENT_PATHS = tuple(
    CHECKER_DOCUMENT_DIRECTORY / f"{identifier}.md" for identifier in sorted(CHECKER_IDS)
)
CHECKER_DOCUMENT_LINKS = tuple(f"checkers/{identifier}.md" for identifier in sorted(CHECKER_IDS))

CONTRACT_ANCHORS = frozenset(
    {
        "installation",
        "configuration",
        "running",
        "triage",
        "per-task-gating",
        "agent-integration",
    }
)

POINTER_SNIPPET = (
    "<!-- code-harness skill pointer -->\n"
    "When adopting, configuring, or running code-harness, or triaging its findings,\n"
    "first read `.agents/skills/code-harness/SKILL.md` and follow it.\n"
)

COMMAND_IN_CODE_SPAN = re.compile(r"`(code-harness[^`]*)`")
PLACEHOLDER = re.compile(r"<[^<>]+>")
LINK_TARGET = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SECOND_LEVEL_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
TRIAGE_HEADING = re.compile(r"^## Triage$", re.MULTILINE)

STALE_SUPPRESSION_WORDING = (
    "Other languages have no suppression mechanism",
    "JavaScript family only",
    "仅 JavaScript 家族",
)
SUPPRESSION_LANGUAGES = ("Python", "Go", "Java", "JavaScript")


def _documented_commands(text: str) -> list[str]:
    """Return each shell command in the text that names the gate executable with arguments."""
    commands: list[str] = []
    fenced = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            commands.extend([stripped] if stripped.startswith("code-harness ") else [])
            continue
        commands.extend(
            candidate.strip()
            for candidate in COMMAND_IN_CODE_SPAN.findall(line)
            if " " in candidate.strip()
        )
    return list(dict.fromkeys(commands))


def _arguments_for(command: str) -> list[str]:
    """Replace documented placeholders and split one command into parser arguments."""
    return shlex.split(PLACEHOLDER.sub("PLACEHOLDER", command))[1:]


def _accepts(arguments: list[str]) -> bool:
    """Report whether the parser accepts exactly one mode; bare --help is the sole exit."""
    try:
        options = _arguments(arguments)
    except SystemExit as exit_error:
        return arguments == ["--help"] and exit_error.code == 0
    return sum((options.all_files, options.staged, options.base is not None)) == 1


def _rejected_commands(path: Path) -> list[str]:
    return [
        command
        for command in _documented_commands(path.read_text(encoding="utf-8"))
        if not _accepts(_arguments_for(command))
    ]


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9\s-]", "", heading.lower()).replace(" ", "-")


def _second_level_slugs(text: str) -> set[str]:
    return {_slug(heading) for heading in SECOND_LEVEL_HEADING.findall(text)}


def _relative_links(path: Path) -> list[str]:
    targets = LINK_TARGET.findall(path.read_text(encoding="utf-8"))
    return [target for target in targets if "://" not in target and not target.startswith("#")]


def _resolves(target: str, document: Path) -> bool:
    """Report whether a link resolves against the directory holding its own document."""
    relative = target.split("#", 1)[0]
    if not relative:
        return True
    return (document.parent / relative).exists()


def _missing_links(path: Path) -> list[str]:
    return [target for target in _relative_links(path) if not _resolves(target, path)]


def _mentions_language(text: str, language: str) -> bool:
    """Match a language name as its own token, so JavaScript never satisfies Java."""
    return re.search(rf"(?<![A-Za-z]){re.escape(language)}(?![A-Za-z])", text) is not None


def _triage_section(path: Path) -> str:
    """Return the Triage section body so its wording can be checked in isolation."""
    text = path.read_text(encoding="utf-8")
    heading = TRIAGE_HEADING.search(text)
    assert heading is not None
    remainder = text[heading.end() :]
    following = SECOND_LEVEL_HEADING.search(remainder)
    return remainder if following is None else remainder[: following.start()]


def test_guide_commands_parse_with_shipped_cli() -> None:
    assert _documented_commands(GUIDE_PATH.read_text(encoding="utf-8"))
    assert _rejected_commands(GUIDE_PATH) == []


def test_skill_commands_parse_with_shipped_cli() -> None:
    assert SKILL_PATH.is_file()
    assert _documented_commands(SKILL_PATH.read_text(encoding="utf-8"))
    assert _rejected_commands(SKILL_PATH) == []


def test_guide_quotes_pointer_snippet_verbatim() -> None:
    assert POINTER_SNIPPET in GUIDE_PATH.read_text(encoding="utf-8")


def test_skill_quotes_pointer_snippet_verbatim() -> None:
    assert SKILL_PATH.is_file()
    assert POINTER_SNIPPET in SKILL_PATH.read_text(encoding="utf-8")


def test_guide_exposes_exactly_the_contract_anchors() -> None:
    assert _second_level_slugs(GUIDE_PATH.read_text(encoding="utf-8")) == CONTRACT_ANCHORS


def test_guide_repository_links_resolve() -> None:
    assert _missing_links(GUIDE_PATH) == []


def test_guide_links_the_agent_reference() -> None:
    assert AGENT_REFERENCE_PATH.is_file()
    assert AGENT_REFERENCE_LINK in _relative_links(GUIDE_PATH)
    assert _resolves(AGENT_REFERENCE_LINK, GUIDE_PATH)


@pytest.mark.parametrize(
    "document",
    [SKILL_PATH, AGENT_REFERENCE_PATH, CHECKER_REFERENCE_PATH, *CHECKER_DOCUMENT_PATHS],
)
def test_skill_bundle_repository_links_resolve(document: Path) -> None:
    assert document.is_file()
    assert _missing_links(document) == []


def test_checker_reference_index_links_every_checker_document() -> None:
    links = _relative_links(CHECKER_REFERENCE_PATH)
    assert [path for path in CHECKER_DOCUMENT_PATHS if not path.is_file()] == []
    assert [link for link in CHECKER_DOCUMENT_LINKS if link not in links] == []


@pytest.mark.parametrize("document", CHECKER_DOCUMENT_PATHS)
def test_checker_document_names_its_own_checker(document: Path) -> None:
    assert f"`{document.stem}`" in document.read_text(encoding="utf-8")


def test_function_size_document_names_every_size_diagnostic() -> None:
    text = (CHECKER_DOCUMENT_DIRECTORY / "function_size.md").read_text(encoding="utf-8")
    assert [
        identifier for identifier in sorted(SIZE_DIAGNOSTIC_IDS) if f"`{identifier}`" not in text
    ] == []


def test_skill_links_the_checker_reference() -> None:
    assert CHECKER_REFERENCE_PATH.is_file()
    assert CHECKER_REFERENCE_LINK in _relative_links(SKILL_PATH)
    assert _resolves(CHECKER_REFERENCE_LINK, SKILL_PATH)


def test_checker_reference_documents_every_checker_and_diagnostic() -> None:
    text = CHECKER_REFERENCE_PATH.read_text(encoding="utf-8")
    assert [identifier for identifier in sorted(CHECKER_IDS) if f"`{identifier}`" not in text] == []
    assert [
        identifier for identifier in sorted(DIAGNOSTIC_IDS) if f"`{identifier}`" not in text
    ] == []


def test_link_resolution_ignores_the_repository_root() -> None:
    assert (REPOSITORY_ROOT / "README.md").is_file()
    assert not (GUIDE_PATH.parent / "README.md").exists()
    assert not _resolves("README.md", GUIDE_PATH)


def test_readme_links_the_guide() -> None:
    assert "docs/getting-started.md" in _relative_links(README_PATH)


@pytest.mark.parametrize("document", [GUIDE_PATH, SKILL_PATH])
def test_guidance_covers_suppression_in_every_supported_language(document: Path) -> None:
    text = document.read_text(encoding="utf-8")
    assert [phrase for phrase in STALE_SUPPRESSION_WORDING if phrase in text] == []
    triage = _triage_section(document)
    assert [
        language for language in SUPPRESSION_LANGUAGES if not _mentions_language(triage, language)
    ] == []


def test_skill_description_announces_suppression_for_every_supported_language() -> None:
    frontmatter = SKILL_PATH.read_text(encoding="utf-8").split("---")[1]
    assert "line suppression" in frontmatter
    assert "every supported language" in frontmatter
    assert "JS-family line suppression" not in frontmatter
