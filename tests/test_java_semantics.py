"""Regression evidence for Java lexical ownership and conservative call resolution."""

import pytest

from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


@pytest.mark.parametrize(
    "content",
    [
        "class E { private static int read() { return 1; } "
        "void run() { java.util.function.IntSupplier r = E::read; } }",
        "class E { private void f(int x) { System.out.println(x); } "
        "private int f(String x) { return x.length(); } void run() { f(1); } }",
        "class E { private int value; void run() { value += 1; } }",
        "class E { int f(int x) { try { return x; } "
        "catch (Exception problem) { throw problem; } } }",
        "class E { @Framework private void entry() {} }",
        "class E { void run() { Runnable empty = () -> {}; } }",
    ],
)
def test_java_resolved_uses_and_external_entry_points(content: str) -> None:
    assert check(Source("E.java", content.encode(), Language.JAVA), Policy()) == ()


@pytest.mark.parametrize(
    "body",
    [
        "int value = 0; value++;",
        "for (int value : xs) System.out.println(value);",
        "try { work(); } catch (Exception value) { throw value; }",
    ],
)
def test_java_locals_do_not_count_as_field_reads(body: str) -> None:
    content = "class E { private int value; void run(int[] xs) { " + body + " } }"
    findings = check(Source("E.java", content.encode(), Language.JAVA), Policy())
    assert sum(f.rule == "unused.field" for f in findings) == 1


@pytest.mark.parametrize("expression", ["convert(Api.fetch())", "new Value(Api.fetch())"])
def test_java_explicit_ingress_conversion(expression: str) -> None:
    content = (
        "import vendor.Api; class Value { Value(String value) { System.out.println(value); } } "
        "class E { String convert(String x) { return x; } "
        "void run() { System.out.println(" + expression + "); }}"
    )
    findings = check(
        Source("E.java", content.encode(), Language.JAVA),
        Policy(third_party_modules=("vendor.Api",)),
    )
    assert findings == ()


def test_java_static_third_party_import_requires_conversion() -> None:
    content = "import static vendor.Api.fetch; class E { String run() { return fetch(); }}"
    findings = check(
        Source("E.java", content.encode(), Language.JAVA),
        Policy(third_party_modules=("vendor.Api.fetch",)),
    )
    assert len(findings) == 1
    assert findings[0].rule == "type.boundary"


def test_java_outbound_objects_preserve_field_ownership() -> None:
    content = (
        "import vendor.Api; class Sent { private int field; } "
        "class Retained { private int field; } "
        "class E { void run() { Api.send(new Sent()); } }"
    )
    findings = check(
        Source("E.java", content.encode(), Language.JAVA),
        Policy(third_party_modules=("vendor.Api",)),
    )
    assert len(findings) == 1
    assert findings[0].rule == "unused.field"
    assert findings[0].column == content.index("field;", content.index("class Retained")) + 1


def test_java_runtime_equality_is_not_identity_dispatch() -> None:
    content = (
        "class E { boolean same(String language, String other) { return language.equals(other); } }"
    )
    findings = check(Source("E.java", content.encode(), Language.JAVA), Policy())
    assert findings == ()
