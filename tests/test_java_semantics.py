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


_ANNOTATION_ARRAY_VOID_CALL = """class Item {
    private void m() {}
}

class E {
    void run() {
        Item[] a = new Item[2];
        a[0].m();
    }
}
"""

_ANNOTATION_ARRAY_DISCARDED_RESULT = """class Item {
    private int m() { return 1; }
}

class E {
    void run() {
        Item[] a = new Item[2];
        a[0].m();
    }
}
"""

_VALUE_INFERRED_ARRAY_VOID_CALL = """class Item {
    private void m() {}
}

class E {
    void run() {
        var b = new Item[]{new Item()};
        b[0].m();
    }
}
"""

_VALUE_INFERRED_ARRAY_DISCARDED_RESULT = """class Item {
    private int m() { return 1; }
}

class E {
    void run() {
        var b = new Item[]{new Item()};
        b[0].m();
    }
}
"""

_NEVER_CALLED_PRIVATE_METHOD = """class Item {
    private void m() {}
}

class E {
    void run() {}
}
"""


@pytest.mark.parametrize(
    "content",
    [_ANNOTATION_ARRAY_VOID_CALL, _VALUE_INFERRED_ARRAY_VOID_CALL],
    ids=["annotation", "value-inferred"],
)
def test_java_array_element_void_calls_resolve(content: str) -> None:
    assert check(Source("E.java", content.encode(), Language.JAVA), Policy()) == ()


@pytest.mark.parametrize(
    "content",
    [_ANNOTATION_ARRAY_DISCARDED_RESULT, _VALUE_INFERRED_ARRAY_DISCARDED_RESULT],
    ids=["annotation", "value-inferred"],
)
def test_java_array_element_discarded_results_warn(content: str) -> None:
    findings = check(Source("E.java", content.encode(), Language.JAVA), Policy())
    assert [(f.rule, f.line, f.column, f.severity) for f in findings] == [
        ("unused.return", 8, 9, "warning")
    ]
    assert "'m'" in findings[0].message


def test_java_never_called_private_method_remains_reported() -> None:
    findings = check(
        Source("E.java", _NEVER_CALLED_PRIVATE_METHOD.encode(), Language.JAVA), Policy()
    )
    assert [(f.rule, f.line, f.column, f.severity) for f in findings] == [
        ("unused.function", 2, 18, "error")
    ]
    assert "'m'" in findings[0].message


_NESTED_ELEMENT_OVERWRITE = """class E {
    static class Item {
        private int m() { return 1; }
    }

    static class Other extends Item {
        private int m() { return 2; }
    }

    void run() {
        var b = new Item[]{new Item()};
        b[0] = new Other();
        b[1].m();
    }
}
"""

_NESTED_ELEMENT_DIFFERENT_NAME = """class E {
    static class Item {
        private int m() { return 1; }
    }

    static class Other {
        private int write() { return 2; }
    }

    void run() {
        var b = new Item[]{new Item()};
        b[0] = new Other();
        b[1].m();
    }
}
"""

_NESTED_ELEMENT_NEVER_CALLED = """class E {
    static class Item {
        private int m() { return 1; }
    }

    static class Other extends Item {
        private int m() { return 2; }

        private int spare() { return 3; }
    }

    void run() {
        var b = new Item[]{new Item()};
        b[0] = new Other();
        b[1].m();
    }
}
"""


def test_java_nested_element_write_keeps_the_called_owner() -> None:
    findings = check(Source("E.java", _NESTED_ELEMENT_OVERWRITE.encode(), Language.JAVA), Policy())
    assert [(f.rule, f.line, f.column, f.severity) for f in findings] == [
        ("unused.return", 13, 9, "warning")
    ]
    assert "'m'" in findings[0].message


def test_java_nested_element_write_of_another_type_keeps_the_owner() -> None:
    findings = check(
        Source("E.java", _NESTED_ELEMENT_DIFFERENT_NAME.encode(), Language.JAVA), Policy()
    )
    assert [(f.rule, f.line, f.column, f.severity) for f in findings] == [
        ("unused.function", 7, 21, "error"),
        ("unused.return", 13, 9, "warning"),
    ]
    assert "'write'" in findings[0].message
    assert "'m'" in findings[1].message


def test_java_nested_element_write_keeps_never_called_method_reported() -> None:
    findings = check(
        Source("E.java", _NESTED_ELEMENT_NEVER_CALLED.encode(), Language.JAVA), Policy()
    )
    assert [(f.rule, f.line, f.column, f.severity) for f in findings] == [
        ("unused.function", 9, 21, "error"),
        ("unused.return", 15, 9, "warning"),
    ]
    assert "'spare'" in findings[0].message
    assert "'m'" in findings[1].message


_JAVA_ELEMENT_INGRESS = """import vendor.Api;

class E {
    void run() {
        int[] items = new int[]{0};
        items[0] = Api.fetch();
    }
}
"""

_JAVA_ELEMENT_INGRESS_TWICE = """import vendor.Api;

class E {
    void run() {
        int[] items = new int[]{0};
        items[0] = Api.fetch();
        items[1] = Api.load();
    }
}
"""

_JAVA_ELEMENT_INGRESS_TYPED = """import vendor.Api;

class E {
    static class Item {
        private final String raw;

        Item(String raw) {
            this.raw = raw;
        }

        private int length() {
            return raw.length();
        }
    }

    void run() {
        var items = new Item[]{new Item("a")};
        items[0] = new Item(Api.fetch());
        System.out.println(items[1].length());
    }
}
"""

_JAVA_REBINDING_INGRESS = """import vendor.Api;

class E {
    void run() {
        String result = Api.fetch();
        System.out.println(result);
    }
}
"""


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param(
            _JAVA_ELEMENT_INGRESS, [("type.boundary", 5, 15, "error")], id="element-write"
        ),
        pytest.param(
            _JAVA_ELEMENT_INGRESS_TWICE, [("type.boundary", 5, 15, "error")], id="two-writes-once"
        ),
        pytest.param(_JAVA_ELEMENT_INGRESS_TYPED, [], id="typed-construction-converts"),
        pytest.param(
            _JAVA_REBINDING_INGRESS, [("type.boundary", 5, 16, "error")], id="plain-rebinding"
        ),
    ],
)
def test_java_element_write_keeps_third_party_ingress_reports(
    content: str, expected: list[tuple[str, int, int, str]]
) -> None:
    findings = check(
        Source("E.java", content.encode(), Language.JAVA),
        Policy(third_party_modules=("vendor.Api",)),
    )
    assert [(f.rule, f.line, f.column, f.severity) for f in findings] == expected
    assert all(
        f.message == "Convert the third-party result into a typed object at ingress"
        for f in findings
    )
