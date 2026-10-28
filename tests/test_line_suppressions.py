"""Exact-line suppression acceptance through the public analysis boundary."""

from dataclasses import dataclass

import pytest

from code_harness.diagnostics import Finding
from code_harness.engine import check
from code_harness.models import Language, Policy, Source

_DIRECTIVE = "// code-harness: ignore-next-line type.broad -- Serialized test input.\n"


def _findings(
    code: str,
    language: Language = Language.TYPESCRIPT,
    touched: frozenset[int] | None = None,
) -> tuple[Finding, ...]:
    return check(Source("test.ts", code.encode(), language, touched), Policy())


@dataclass(frozen=True)
class _LanguageFixture:
    """Bind one grammar's marker, registered rule and single-finding target."""

    language: Language
    path: str
    marker: str
    rule: str
    prefix: str
    target: str
    clean_target: str
    suffix: str = ""
    trailer: str = ""

    def directive(self, rule: str | None = None, reason: str = "Reason.") -> str:
        selected = self.rule if rule is None else rule
        return f"{self.marker} code-harness: ignore-next-line {selected} -- {reason}\n"

    def source(self, middle: str, target_override: str | None = None) -> str:
        selected = self.target if target_override is None else target_override
        return self.prefix + middle + selected + self.suffix + self.trailer

    @property
    def directive_line(self) -> int:
        return self.prefix.count("\n") + 1

    @property
    def target_line(self) -> int:
        return self.directive_line + 1

    @property
    def last_line(self) -> int:
        return self.target_line + self.suffix.count("\n") + self.trailer.count("\n")


def _analyze(
    fixture: _LanguageFixture,
    middle: str,
    target_override: str | None = None,
    touched: frozenset[int] | None = None,
) -> tuple[Finding, ...]:
    source = Source(
        fixture.path,
        fixture.source(middle, target_override).encode(),
        fixture.language,
        touched,
    )
    return check(source, Policy())


_PYTHON = _LanguageFixture(
    Language.PYTHON,
    "test.py",
    "#",
    "type.annotation",
    "",
    "x: object = 1\n",
    "previous = 1\n",
    trailer="other = 1\n",
)
_GO = _LanguageFixture(
    Language.GO,
    "test.go",
    "//",
    "type.broad",
    "package sample\n",
    "type Input any\n",
    "type Input int\n",
    trailer="var other = 1\n",
)
_JAVA = _LanguageFixture(
    Language.JAVA,
    "Test.java",
    "//",
    "type.broad",
    "class Test {\n",
    "void run(Object value) { consume(value); }\n",
    "void run() { consume(1); }\n",
    suffix="}\n",
)
_JAVASCRIPT = _LanguageFixture(
    Language.JAVASCRIPT,
    "test.js",
    "//",
    "type.broad",
    "",
    "const input = JSON.stringify(payload);\n",
    "const input = 1;\n",
)
_TYPESCRIPT = _LanguageFixture(
    Language.TYPESCRIPT,
    "test.ts",
    "//",
    "type.broad",
    "",
    "const input = JSON.stringify(payload);\n",
    "const input = 1;\n",
)
_TSX = _LanguageFixture(
    Language.TSX,
    "test.tsx",
    "//",
    "type.broad",
    "",
    "const input = JSON.stringify(payload);\n",
    "const input = 1;\n",
)
_ALL_LANGUAGES = (_PYTHON, _GO, _JAVA, _JAVASCRIPT, _TYPESCRIPT, _TSX)
_NEW_LANGUAGES = (_PYTHON, _GO, _JAVA)
_ALL_IDS = [fixture.language.value for fixture in _ALL_LANGUAGES]
_NEW_IDS = [fixture.language.value for fixture in _NEW_LANGUAGES]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
@pytest.mark.parametrize(
    "target",
    [
        "const input = JSON.stringify(payload);\n",
        "assert.equal(result.content, JSON.stringify(expected));\n",
        "consume(JSON.stringify(first), JSON.stringify(second));\n",
    ],
)
def test_approved_encodings_are_suppressed(language: Language, target: str) -> None:
    assert _findings(_DIRECTIVE + target, language) == ()
    assert any(f.rule == "type.broad" for f in _findings(target, language))


def test_generic_result_inference_precedes_exact_line_suppression() -> None:
    declaration = "function transact<R>(work: () => R): R { return work(); }\n"
    directive = _DIRECTIVE.replace("type.broad", "unused.return")
    findings = _findings(declaration + directive + "transact(() => 1);\ntransact(() => 2);\n")
    assert [(f.rule, f.line, f.column) for f in findings] == [("unused.return", 4, 1)]
    stale = _findings(declaration + directive + "transact(() => {});\n")
    assert [(f.rule, f.line) for f in stale] == [("type.suppression", 2)]


def test_exact_rule_all_occurrences_and_adjacent_lines() -> None:
    code = _DIRECTIVE + "const input: unknown = JSON.stringify(payload) as any;\n"
    code += "const adjacent = JSON.stringify(payload);\n"
    assert [(f.rule, f.line) for f in _findings(code)] == [
        ("type.assertion", 2),
        ("type.broad", 3),
    ]


def test_nested_multiline_encoding_keeps_later_diagnostic() -> None:
    code = _DIRECTIVE + "consume(JSON.stringify({\n  nested: JSON.stringify(payload),\n}));\n"
    assert [(f.rule, f.line) for f in _findings(code)] == [("type.broad", 3)]


@pytest.mark.parametrize(
    "comment",
    [
        "// code-harness: ignore-next-line missing.rule -- Reason.",
        "// code-harness: ignore-next-line * -- Reason.",
        "// code-harness: ignore-next-line type.broad,type.assertion -- Reason.",
        "// code-harness: ignore-next-line type.broad type.assertion -- Reason.",
        "// code-harness: ignore-next-line type.suppression -- Reason.",
        "// code-harness: ignore-next-line type.broad",
        "// code-harness: ignore-next-line type.broad --   ",
        "// code-harness: ignore-next-line -- Reason.",
        "// code-harness: ignore-file type.broad -- Reason.",
        "// code-harness: ignore-next-line type.broad - Reason.",
        "/* code-harness: ignore-next-line type.broad -- Reason. */",
        "const previous = 1; // code-harness: ignore-next-line type.broad -- Reason.",
    ],
)
def test_invalid_directives_fail_closed(comment: str) -> None:
    findings = _findings(comment + "\nconst input = JSON.stringify(payload);\n")
    assert [(f.rule, f.line) for f in findings] == [
        ("type.suppression", 1),
        ("type.broad", 2),
    ]


@pytest.mark.parametrize("gap", ["\n", "// explanation\n", "const other = 1;\n"])
def test_target_is_immediately_following_physical_line(gap: str) -> None:
    findings = _findings(_DIRECTIVE + gap + "const input = JSON.stringify(payload);\n")
    assert [(f.rule, f.line) for f in findings] == [
        ("type.suppression", 1),
        ("type.broad", 3),
    ]
    assert "Unused" in findings[0].message


@pytest.mark.parametrize("target", ["", "const plain = 1;\n", "const asserted = value as Value;\n"])
def test_stale_directive_is_an_error(target: str) -> None:
    findings = _findings(_DIRECTIVE + target)
    assert findings[0].rule == "type.suppression"
    assert "Unused" in findings[0].message


@pytest.mark.parametrize(
    "code",
    [
        'const text = "// code-harness: ignore-next-line type.broad -- Reason.";\n',
        "const text = `\n// code-harness: ignore-next-line type.broad -- Reason.\n`;\n",
    ],
)
def test_literal_directive_text_has_no_effect(code: str) -> None:
    findings = _findings(code + "const input = JSON.stringify(payload);\n")
    assert [f.rule for f in findings] == ["type.broad"]


def test_other_suppression_directives_remain_prohibited() -> None:
    code = _DIRECTIVE + "// @ts-ignore\nconst input = JSON.stringify(payload);\n"
    assert [(f.rule, f.line) for f in _findings(code)] == [
        ("type.suppression", 1),
        ("type.suppression", 2),
        ("type.broad", 3),
    ]


def test_another_registered_diagnostic_can_be_selected() -> None:
    code = _DIRECTIVE.replace("type.broad", "type.assertion")
    code += "const input: unknown = payload as Payload;\n"
    assert [(f.rule, f.line) for f in _findings(code)] == [("type.broad", 2)]


@pytest.mark.parametrize(
    ("language", "path", "code", "expected"),
    [
        (
            Language.PYTHON,
            "test.py",
            "from typing import Any\n"
            "# code-harness: ignore-next-line type.broad -- Reason.\n"
            "x: Any = 1\n",
            [("type.annotation", 3)],
        ),
        (
            Language.JAVA,
            "Test.java",
            "class Test {\n"
            "// code-harness: ignore-next-line type.broad -- Reason.\n"
            "Object value;\n}\n",
            [("unused.field", 3)],
        ),
    ],
    ids=[Language.PYTHON.value, Language.JAVA.value],
)
def test_selected_rule_leaves_other_registered_findings(
    language: Language, path: str, code: str, expected: list[tuple[str, int]]
) -> None:
    findings = check(Source(path, code.encode(), language), Policy())
    assert [(f.rule, f.line) for f in findings] == expected


def test_indented_crlf_directive_and_reason_are_supported() -> None:
    code = "  " + _DIRECTIVE.replace("Serialized test input.", "Replaces @ts-ignore fixture.")
    code += "const input = JSON.stringify(payload);\n"
    assert _findings(code.replace("\n", "\r\n")) == ()


@pytest.mark.parametrize("target", ["const input = JSON.stringify(payload);", "const input = 1;"])
def test_out_of_scope_target_does_not_report_unused(target: str) -> None:
    code = _DIRECTIVE + target + "\nexport const changed = 1;\n"
    assert _findings(code, touched=frozenset({3})) == ()


def test_changed_target_reports_stale_directive_outside_scope() -> None:
    assert [
        f.rule for f in _findings(_DIRECTIVE + "const input = 1;\n", touched=frozenset({2}))
    ] == ["type.suppression"]


def test_comment_only_change_selects_target_and_preserves_other_rules() -> None:
    code = _DIRECTIVE + "const input = JSON.stringify(payload) as Payload;\n"
    assert [(f.rule, f.line) for f in _findings(code, touched=frozenset({1}))] == [
        ("type.assertion", 2)
    ]


def test_suppression_cannot_escape_to_another_source() -> None:
    code = _DIRECTIVE + "const input = JSON.stringify(payload);\n"
    assert _findings(code) == ()
    findings = check(
        Source("other.ts", b"const input = JSON.stringify(payload);", Language.TYPESCRIPT), Policy()
    )
    assert [(f.path, f.rule) for f in findings] == [("other.ts", "type.broad")]


@pytest.mark.parametrize("fixture", _ALL_LANGUAGES, ids=_ALL_IDS)
def test_every_supported_language_suppresses_the_exact_next_line(
    fixture: _LanguageFixture,
) -> None:
    assert [f.rule for f in _analyze(fixture, "")] == [fixture.rule]
    assert _analyze(fixture, fixture.directive()) == ()


_INVALID_BODIES = (
    "ignore-next-line missing.rule -- Reason.",
    "ignore-next-line * -- Reason.",
    "ignore-next-line type.broad,type.annotation -- Reason.",
    "ignore-next-line type.broad type.assertion -- Reason.",
    "ignore-next-line type.suppression -- Reason.",
    "ignore-next-line {rule}",
    "ignore-next-line {rule} --   ",
    "ignore-next-line -- Reason.",
    "ignore-file {rule} -- Reason.",
    "ignore-next-line {rule} - Reason.",
)


@pytest.mark.parametrize("fixture", _NEW_LANGUAGES, ids=_NEW_IDS)
@pytest.mark.parametrize("body", _INVALID_BODIES)
def test_malformed_directive_forms_are_rejected(fixture: _LanguageFixture, body: str) -> None:
    middle = f"{fixture.marker} code-harness: {body.format(rule=fixture.rule)}\n"
    assert [(f.rule, f.line) for f in _analyze(fixture, middle)] == [
        ("type.suppression", fixture.directive_line),
        (fixture.rule, fixture.target_line),
    ]


@pytest.mark.parametrize("fixture", (_GO, _JAVA), ids=(Language.GO.value, Language.JAVA.value))
def test_block_comment_directive_is_rejected(fixture: _LanguageFixture) -> None:
    middle = f"/* code-harness: ignore-next-line {fixture.rule} -- Reason. */\n"
    assert [(f.rule, f.line) for f in _analyze(fixture, middle)] == [
        ("type.suppression", fixture.directive_line),
        (fixture.rule, fixture.target_line),
    ]


@pytest.mark.parametrize(
    ("language", "path", "code", "expected"),
    [
        (
            Language.PYTHON,
            "test.py",
            "previous = 1  # code-harness: ignore-next-line type.annotation -- Reason.\n"
            "x: object = 1\n",
            {("type.suppression", 1), ("type.annotation", 2)},
        ),
        (
            Language.GO,
            "test.go",
            "package sample\n"
            "var previous = 1 // code-harness: ignore-next-line type.broad -- Reason.\n"
            "type Input any\n",
            {("type.suppression", 2), ("type.broad", 3)},
        ),
        (
            Language.JAVA,
            "Test.java",
            "class Test {\n"
            "void run(Object value) { consume(value); } "
            "// code-harness: ignore-next-line type.broad -- Reason.\n}\n",
            {("type.suppression", 2), ("type.broad", 2)},
        ),
    ],
    ids=[Language.PYTHON.value, Language.GO.value, Language.JAVA.value],
)
def test_trailing_directive_is_rejected(
    language: Language, path: str, code: str, expected: set[tuple[str, int]]
) -> None:
    findings = check(Source(path, code.encode(), language), Policy())
    assert {(f.rule, f.line) for f in findings} == expected


@pytest.mark.parametrize(
    ("language", "path", "code", "rule", "target_line"),
    [
        (
            Language.PYTHON,
            "test.py",
            'TEXT = "# code-harness: ignore-next-line type.annotation -- Reason."\nx: object = 1\n',
            "type.annotation",
            2,
        ),
        (
            Language.PYTHON,
            "test.py",
            "def run() -> None:\n"
            '    """# code-harness: ignore-next-line type.annotation -- Reason."""\n'
            "    x: object = 1\n",
            "type.annotation",
            3,
        ),
        (
            Language.GO,
            "test.go",
            'package sample\nvar text = "// code-harness: ignore-next-line type.broad -- Reason."\n'
            "type Input any\n",
            "type.broad",
            3,
        ),
        (
            Language.GO,
            "test.go",
            "package sample\nvar text = `// code-harness: ignore-next-line type.broad -- Reason.`\n"
            "type Input any\n",
            "type.broad",
            3,
        ),
        (
            Language.JAVA,
            "Test.java",
            "class Test {\n"
            'void first() { consume("// code-harness: ignore-next-line type.broad -- Reason."); }\n'
            "void run(Object value) { consume(value); }\n}\n",
            "type.broad",
            3,
        ),
    ],
    ids=["python-string", "python-docstring", "go-string", "go-raw-string", "java-string"],
)
def test_literal_directive_text_has_no_effect_in_any_language(
    language: Language, path: str, code: str, rule: str, target_line: int
) -> None:
    findings = check(Source(path, code.encode(), language), Policy())
    assert [(f.rule, f.line) for f in findings] == [(rule, target_line)]


@pytest.mark.parametrize("fixture", _NEW_LANGUAGES, ids=_NEW_IDS)
def test_stale_directive_is_an_error_in_any_language(fixture: _LanguageFixture) -> None:
    findings = _analyze(fixture, fixture.directive(), target_override=fixture.clean_target)
    assert [f.rule for f in findings] == ["type.suppression"]
    assert "Unused" in findings[0].message


@pytest.mark.parametrize("fixture", _NEW_LANGUAGES, ids=_NEW_IDS)
def test_comment_only_change_selects_and_suppresses_the_target(
    fixture: _LanguageFixture,
) -> None:
    assert _analyze(fixture, fixture.directive(), touched=frozenset({fixture.directive_line})) == ()


@pytest.mark.parametrize("fixture", _NEW_LANGUAGES, ids=_NEW_IDS)
def test_out_of_scope_target_does_not_report_unused_in_any_language(
    fixture: _LanguageFixture,
) -> None:
    assert fixture.last_line > fixture.target_line
    stale = _analyze(fixture, fixture.directive(), target_override=fixture.clean_target)
    assert [f.rule for f in stale] == ["type.suppression"]
    assert "Unused" in stale[0].message
    assert (
        _analyze(
            fixture,
            fixture.directive(),
            target_override=fixture.clean_target,
            touched=frozenset({fixture.last_line}),
        )
        == ()
    )


@pytest.mark.parametrize("fixture", _NEW_LANGUAGES, ids=_NEW_IDS)
def test_changed_target_reports_stale_directive_outside_scope_in_any_language(
    fixture: _LanguageFixture,
) -> None:
    findings = _analyze(
        fixture,
        fixture.directive(),
        target_override=fixture.clean_target,
        touched=frozenset({fixture.target_line}),
    )
    assert [f.rule for f in findings] == ["type.suppression"]


@pytest.mark.parametrize("fixture", _NEW_LANGUAGES, ids=_NEW_IDS)
@pytest.mark.parametrize("body", ("noqa", "type: ignore", "nolint", "@ts-ignore", "eslint-disable"))
def test_foreign_directives_remain_prohibited_in_every_language(
    fixture: _LanguageFixture, body: str
) -> None:
    findings = _analyze(fixture, f"{fixture.marker} {body}\n")
    assert [(f.rule, f.line) for f in findings] == [
        ("type.suppression", fixture.directive_line),
        (fixture.rule, fixture.target_line),
    ]


@pytest.mark.parametrize("marker", ["NOSONAR", "nosonar", "CHECKSTYLE:OFF", "noinspection"])
def test_java_reason_citing_a_foreign_marker_reports_the_directive_line(marker: str) -> None:
    code = (
        "class Test {\n"
        f"// code-harness: ignore-next-line type.broad -- Kept inline {marker}.\n"
        "void run(Object value) { consume(value); }\n}\n"
    )
    findings = check(Source("Test.java", code.encode(), Language.JAVA), Policy())
    assert [(f.rule, f.line) for f in findings] == [("type.suppression", 2)]


@pytest.mark.parametrize("touched", [frozenset({1}), frozenset({2}), frozenset({3})])
def test_malformed_directive_respects_partial_scope(touched: frozenset[int]) -> None:
    code = "// code-harness: ignore-next-line missing.rule -- Reason.\n"
    code += "const input = JSON.stringify(payload);\nexport const other = 1;\n"
    findings = _findings(code, touched=touched)
    expected = [] if touched == frozenset({3}) else ["type.suppression", "type.broad"]
    assert [f.rule for f in findings] == expected


@pytest.mark.parametrize(
    ("configuration", "expected"),
    [
        ('{"checkers":{"type.broad":{"enabled":false}}}', ["type.suppression"]),
        ('{"checkers":{"type.suppression":{"enabled":false}}}', []),
    ],
)
def test_existing_checker_flags_apply_to_directive_validation(
    configuration: str, expected: list[str]
) -> None:
    source = Source(
        "test.ts",
        (_DIRECTIVE + "const input = JSON.stringify(payload);\n").encode(),
        Language.TYPESCRIPT,
    )
    assert [f.rule for f in check(source, Policy.model_validate_json(configuration))] == expected
