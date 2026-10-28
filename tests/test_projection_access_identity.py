"""Projection evidence preserves runtime field access and construction semantics."""

import pytest

from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


def _count(code: str, language: Language = Language.PYTHON) -> int:
    return sum(
        finding.rule == "structure.guarded_projection"
        for finding in check(Source("sample", code.encode(), language), Policy())
    )


@pytest.mark.parametrize(
    ("guard", "value"),
    [
        ("s.{f}", 's["{f}"]'),
        ('s["{f}"]', "s.{f}"),
        ("s.inner.{f}", 's["inner"].{f}'),
        ('s["inner"].{f}', "s.inner.{f}"),
    ],
)
def test_python_attribute_and_item_reads_are_different_values(guard: str, value: str) -> None:
    body = "\n".join(
        f" if {guard.format(f=f)} is not None: t.{f} = {value.format(f=f)}" for f in "abc"
    )
    assert _count(f"def project(s:S,t:T)->None:\n{body}\n") == 0


@pytest.mark.parametrize("receiver", ["s", "t"])
def test_python_nested_attribute_and_item_receivers_split_clusters(receiver: str) -> None:
    first = " if s.inner.a is not None: t.inner.a = s.inner.a\n"
    remainder = "\n".join(
        f" if s.inner.{f} is not None: t.inner.{f} = s.inner.{f}" for f in "bc"
    ).replace(receiver + ".inner", receiver + '["inner"]')
    assert _count("def project(s:S,t:T)->None:\n" + first + remainder + "\n") == 0


def test_python_attribute_and_item_destinations_are_distinct_fields() -> None:
    code = """def project(s:S,t:T)->None:
 if s.a is not None: t.x = s.a
 if s.b is not None: t["x"] = s.b
 if s.c is not None: t.y = s.c
"""
    assert _count(code) == 1


@pytest.mark.parametrize("key", ['"{f}", operation()', '"{f}", "other"', '"{f}",'])
@pytest.mark.parametrize("position", ["guard", "value", "destination"])
def test_python_tuple_indexes_do_not_establish_scalar_field_evidence(
    key: str, position: str
) -> None:
    templates = {
        "guard": f' if s[{key}] is not None: t.{{f}} = s["{{f}}"]',
        "value": f' if s["{{f}}"] is not None: t.{{f}} = s[{key}]',
        "destination": f' if s["{{f}}"] is not None: t[{key}] = s["{{f}}"]',
    }
    body = "\n".join(templates[position].format(f=f) for f in "abc")
    assert _count(f"def project(s:S,t:T)->None:\n{body}\n") == 0


def test_python_matching_scalar_item_reads_remain_supported() -> None:
    body = "\n".join(f' if s["{f}"] is not None: t["{f}"] = s["{f}"]' for f in "abc")
    assert _count(f"def project(s:S,t:T)->None:\n{body}\n") == 1


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
@pytest.mark.parametrize(
    ("key", "expected"), [("__proto__", 0), ('"__proto__"', 0), ('["__proto__"]', 1)]
)
def test_script_prototype_setters_are_not_spread_properties(
    language: Language, key: str, expected: int
) -> None:
    code = "function project(s) { return {"
    code += "...(s.a != null && {a:s.a}), ...(s.b != null && {b:s.b}),"
    code += f"...(s.c != null && {{{key}:s.c}})" + "}; }"
    assert _count(code, language) == expected
