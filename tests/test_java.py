"""Java grammar integration through the public analysis and CLI seams."""

from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import Finding, Report
from code_harness.engine import check
from code_harness.plugins.builtins import builtin_registry
from code_harness.policy.models import (
    Boundary,
    Checkers,
    FunctionSizeOptions,
    ImportOptions,
    Policy,
)
from code_harness.source import Language, Source


def _check(content: str, policy: Policy | None = None) -> tuple[Finding, ...]:
    return check(
        Source("Example.java", content.encode(), Language.JAVA),
        policy if policy is not None else Policy(),
    )


@pytest.mark.parametrize(
    ("declaration", "rule"),
    [
        ("Object value;", "type.broad"),
        ("java.lang.Object value;", "type.broad"),
        ("java.util.List<?> value;", "type.broad"),
        ("java.util.Map value;", "type.broad"),
        ("String get(String value) { return (String) value; }", "type.assertion"),
        ('@SuppressWarnings("unchecked") String value;', "type.suppression"),
        (
            '@java.lang.SuppressWarnings({"rawtypes", "unchecked"}) String value;',
            "type.suppression",
        ),
        ("// NOSONAR\nString value;", "type.suppression"),
        ("/* CHECKSTYLE:OFF */ String value;", "type.suppression"),
        ("// noinspection unchecked\nString value;", "type.suppression"),
        ("// noqa\nString value;", "type.suppression"),
    ],
)
def test_java_type_and_suppression_diagnostics(declaration: str, rule: str) -> None:
    findings = _check("class Example { " + declaration + " }")
    assert len([finding for finding in findings if finding.rule == rule]) == 1


@pytest.mark.parametrize(
    "content",
    [
        "class Example { int convert(long value) { return (int) value; } }",
        "class Example { java.util.List<String> get(java.util.List<String> value) "
        "{ return value; } }",
        "class Example { java.util.List<? extends String> "
        "get(java.util.List<? extends String> value) { return value; } }",
        "class Example<Object> { Object get(Object value) { return value; } }",
        "class Object {} class Example { Object get(Object value) { return value; } }",
        "import app.Object; class Example { Object get(Object value) { return value; } }",
        "class List {} class Example { List get(List value) { return value; } }",
        'class Example { String get() { return "Object NOSONAR @SuppressWarnings"; } }',
        "interface Example { String get(String value); }",
        "record Example(int value) { Example { "
        "if (value < 0) throw new IllegalArgumentException(); } }",
    ],
)
def test_java_concrete_contracts_remain_clean(content: str) -> None:
    assert _check(content) == ()


def test_java_imported_raw_collection_is_reported() -> None:
    findings = _check("import java.util.List; class Example { List value; }")
    assert any(f.rule == "type.broad" and "List" in f.message for f in findings)


def test_java_lexical_reads_preserve_field_owners_and_parameter_scopes() -> None:
    findings = _check("""
class Example {
    private int used, written;
    Example(int value) { this.used = value; }
    int read(Example other, int ignored) { written = 1; return other.used; }
    private int dead(int value) { return value; }
    void run() { read(this, 1); }
}
class Other { private int used; }
""")
    assert {(f.rule, f.line) for f in findings} == {
        ("unused.field", 3),
        ("unused.parameter", 5),
        ("unused.function", 6),
        ("unused.return", 7),
        ("unused.field", 9),
    }
    assert next(f for f in findings if f.rule == "unused.return").severity == "warning"


def test_java_lambdas_varargs_and_receiver_parameters() -> None:
    findings = _check("""
class Example {
    void run(Example this, String... values) {
        java.util.function.Function<String, String> first = value -> value;
        java.util.function.Function<String, String> second = (ignored) -> "constant";
        System.out.println(values.length);
    }
}
""")
    assert len(findings) == 1
    assert findings[0].rule == "unused.parameter"
    assert "ignored" in findings[0].message


@pytest.mark.parametrize(
    ("content", "options", "rule", "actual"),
    [
        ("class E { E(int a, int b) {} }", FunctionSizeOptions(parameters=1), "size.parameters", 2),
        (
            "record E(int a, int b) { E {} }",
            FunctionSizeOptions(parameters=1),
            "size.parameters",
            2,
        ),
        (
            "class E { void f(E this, String... a) {} }",
            FunctionSizeOptions(parameters=1),
            "size.parameters",
            0,
        ),
        (
            "class E { void f() { int a = 1; a++; } }",
            FunctionSizeOptions(statements=1),
            "size.statements",
            2,
        ),
        (
            "class E { void f(int[] xs) { for (int x : xs) { if(x > 0) break; } } }",
            FunctionSizeOptions(nesting=1),
            "size.nesting",
            2,
        ),
        (
            "class E { int f(int x) { return switch(x) "
            "{ case 1 -> 2; case 2 -> 3; default -> 0; }; } }",
            FunctionSizeOptions(complexity=2),
            "size.complexity",
            3,
        ),
        (
            "class E { boolean f(boolean a, boolean b) { return a && b || a; } }",
            FunctionSizeOptions(complexity=2),
            "size.complexity",
            3,
        ),
    ],
)
def test_java_function_metrics(
    content: str,
    options: FunctionSizeOptions,
    rule: str,
    actual: int,
) -> None:
    findings = [
        f
        for f in _check(content, Policy(checkers=Checkers(function_size=options)))
        if f.rule == rule
    ]
    if actual == 0:
        assert findings == []
    else:
        assert len(findings) == 1
        assert f"is {actual};" in findings[0].message


def test_java_comments_do_not_count_as_function_lines() -> None:
    content = "class E {\nvoid run() {\n/* long\ncomment */\n// rationale\n}\n}"
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(lines=2)))
    assert _check(content, policy) == ()


def test_java_nested_lambda_has_independent_complexity() -> None:
    content = "class E { void run() { Runnable r = () -> { if (ready()) work(); }; } }"
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(complexity=1)))
    findings = [f for f in _check(content, policy) if f.rule == "size.complexity"]
    assert len(findings) == 1
    assert findings[0].column == content.index("() ->") + 1


@pytest.mark.parametrize("target", ["vendor.Api", "static vendor.Api.send", "vendor.*"])
def test_java_imports_enforce_architecture_boundaries(target: str) -> None:
    boundary = Boundary(name="restricted", sources=("*.java",), forbidden_imports=("vendor.*",))
    policy = Policy(checkers=Checkers(architecture_import=ImportOptions(boundaries=(boundary,))))
    findings = _check(f"import {target}; class Example {{}}", policy)
    assert len(findings) == 1
    assert findings[0].rule == "architecture.import"
    assert findings[0].line == 1
    assert findings[0].column == 1


@pytest.mark.parametrize(
    "expression",
    [
        "language == Kind.JAVA",
        'language == "java"',
        'language.equals("java")',
        '"java".equals(language)',
        "switch(language) { default -> false; }",
    ],
)
def test_java_identity_dispatch(expression: str) -> None:
    content = "class E { boolean select(String language) { return " + expression + "; } }"
    assert any(f.rule == "architecture.dispatch" for f in _check(content))


def test_java_extends_and_implements_share_resolved_parameter_reads() -> None:
    findings = _check("""
interface Contract { int call(int value); }
class Base { int call(int input) { return input; } }
class Example extends Base implements Contract { int call(int unused) { return 1; } }
""")
    assert findings == ()


def test_java_explicit_import_links_peer_fields() -> None:
    sources = (
        Source(
            "domain/Value.java",
            b"package domain; public class Value { public int number; }",
            Language.JAVA,
        ),
        Source(
            "app/Example.java",
            b"package app; import domain.Value; "
            b"class Example { int read(Value value) { return value.number; } }",
            Language.JAVA,
        ),
    )
    assert builtin_registry().analyze_sources(sources, Policy()) == ()


def test_java_third_party_result_requires_ingress_conversion() -> None:
    content = "import vendor.Api; class Example { String run() { return Api.fetch(); } }"
    findings = _check(content, Policy(third_party_modules=("vendor.Api",)))
    assert len(findings) == 1
    assert findings[0].rule == "type.boundary"


def test_java_discovery_and_cli_preserve_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}\n")
    source = tmp_path / "Example.java"
    content = b"class Example { Object value; }"
    source.write_bytes(content)
    assert builtin_registry().language_for(source.name) == Language.JAVA
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.files == 1
    assert any(f.rule == "type.broad" for f in report.findings)
    assert source.read_bytes() == content


def test_java_recovered_syntax_warns_and_keeps_type_findings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    findings = _check("class Example { Object value; void broken( { }")
    assert any(f.rule == "type.broad" for f in findings)
    assert "syntax" in caplog.text.lower()
    assert not any(f.rule.startswith("unused.") for f in findings)
