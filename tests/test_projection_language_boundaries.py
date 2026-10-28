"""Conservative projection exclusions and region boundaries outside JavaScript."""

import pytest

from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


def _count(code: str, language: Language) -> int:
    return sum(
        finding.rule == "structure.guarded_projection"
        for finding in check(Source("sample", code.encode(), language), Policy())
    )


@pytest.mark.parametrize(
    "statement",
    [
        "if s.{f} is not None:\n  t.{f} = s.{f} + 1",
        "if s.{f} is not None:\n  t.{f} = convert(s.{f})",
        "if s.{f} is not None:\n  t.{f} = s.{f}\n  audit()",
        "if s.{f} is not None:\n  return s.{f}",
        "if s.{f} is not None:\n  raise ValueError()",
        "if s.{f}:\n  t.{f} = s.{f}",
        "if s.{f} is not None and ready:\n  t.{f} = s.{f}",
        "if s[key] is not None:\n  t.{f} = s[key]",
        "if s.{f} is not None:\n  t[key] = s.{f}",
        "if s().{f} is not None:\n  t.{f} = s().{f}",
        "if s.{f} is not None:\n  t.{f} = s.{f}\n else:\n  t.{f} = 0",
        "if s.{f} is not None:\n  t.{f} = other.{f}",
        "if s.{f} is not None:\n  t.{f} = s.other",
        "if s.{f} is not None:\n  t.{f} += s.{f}",
    ],
)
def test_python_operations_are_not_projections(statement: str) -> None:
    code = "def f(s: S,t: T,key: str) -> None:\n "
    code += "\n ".join(statement.format(f=f) for f in "abc")
    assert _count(code, Language.PYTHON) == 0


@pytest.mark.parametrize(
    "statement",
    [
        "if s.{f} != nil {{ t.{f} = convert(s.{f}) }}",
        "if s.{f} != nil {{ t.{f} = s.{f}; audit() }}",
        "if s.{f} != nil {{ return }}",
        "if s.{f} != nil && ready {{ t.{f} = s.{f} }}",
        'if s["{f}"] != nil {{ t.{f} = s["{f}"] }}',
        "if s().{f} != nil {{ t.{f} = s().{f} }}",
        "if s.{f} != nil {{ t.{f} = s.{f} }} else {{t.{f} = fallback}}",
        "if s.{f} != nil {{ t.{f} += s.{f} }}",
        "if x := operation(); s.{f} != nil {{ t.{f} = s.{f} }}",
        "if s.{f} != nil {{ t.{f}, other = s.{f}, value }}",
    ],
)
def test_go_operations_are_not_projections(statement: str) -> None:
    code = "package p\nfunc F(s S,t T) {\n"
    code += "\n".join(statement.format(f=f) for f in "ABC") + "\n}"
    assert _count(code, Language.GO) == 0


@pytest.mark.parametrize(
    "statement",
    [
        "if(s.{f} != null) t.{f} = convert(s.{f});",
        "if(s.{f} != null) {{t.{f} = s.{f}; audit();}}",
        "if(s.{f} != null) return;",
        "if(s.{f} != null) throw new Error();",
        "if(s.{f} != null && ready) t.{f} = s.{f};",
        "if(s.get().{f} != null) t.{f} = s.get().{f};",
        "if(s.{f} != null) t.get().{f} = s.{f};",
        "if(s.{f} != null) t.{f} = s.{f}; else t.{f} = fallback;",
        "if(s.{f} != null) t.{f} += s.{f};",
        "if(s.{f} != null) t.{f} = s.other;",
    ],
)
def test_java_operations_are_not_projections(statement: str) -> None:
    code = "class C { void f(S s,T t) {\n"
    code += "\n".join(statement.format(f=f) for f in "abc") + "\n}}"
    assert _count(code, Language.JAVA) == 0


@pytest.mark.parametrize("name", ["nil", "true", "false"])
def test_go_shadowed_predeclared_values(name: str) -> None:
    code = f"package p\nfunc F(s S,t T,{name} int) {{\n"
    code += "\n".join(f"if s.{f} == {name} {{t.{f} = {name}}}" for f in "ABC") + "\n}"
    assert _count(code, Language.GO) == 0


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "def f(s:S,t:T)->None:\n if s.a is not None: t.a=s.a\n"
            " if s.b is not None: t.b=s.b\n audit()\n if s.c is not None: t.c=s.c\n",
        ),
        (
            Language.GO,
            "package p\nfunc F(s S,t T) {if s.A != nil {t.A=s.A};\n"
            "if s.B != nil {t.B=s.B}; audit(); if s.C != nil {t.C=s.C}}",
        ),
        (
            Language.JAVA,
            "class C {void f(S s,T t) {if(s.a != null)t.a=s.a;"
            "if(s.b != null)t.b=s.b; audit(); if(s.c != null)t.c=s.c;}}",
        ),
    ],
)
def test_other_language_calls_split_regions(language: Language, code: str) -> None:
    assert _count(code, language) == 0
