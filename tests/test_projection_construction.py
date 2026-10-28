"""Literal construction identities must preserve keys and runtime boundaries."""

import pytest

from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


def _count(code: str, language: Language) -> int:
    return sum(
        finding.rule == "structure.guarded_projection"
        for finding in check(Source("sample", code.encode(), language), Policy())
    )


def test_python_dictionary_expression_keys_are_not_static_names() -> None:
    entries = ",".join(
        f"**({{{name}: source.{name}}} if source.{name} is not None else {{}})" for name in "abc"
    )
    code = f"def f(source: S, a: str, b: str, c: str) -> T:\n return {{{entries}}}\n"
    assert _count(code, Language.PYTHON) == 0


@pytest.mark.parametrize(("key", "expected"), [('"{f}"', 1), ("{f}", 0)])
def test_script_computed_keys_require_literal_evidence(key: str, expected: int) -> None:
    entries = ",".join(
        f"...(source.{name} != null && {{[{key.format(f=name)}]: source.{name}}})" for name in "abc"
    )
    code = f"function f(source,a,b,c) {{ return {{{entries}}}; }}"
    assert _count(code, Language.TYPESCRIPT) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "...(source.{f} != null ? {{{f}:source.{f}}} : {{fallback:0}})",
        "...(source.{f} != null && {{{f}:source.{f}, extra:1}})",
        "...(source.{f} && {{{f}:source.{f}}})",
        "...(source.{f} != null && {{{f}:convert(source.{f})}})",
        "...(source.{f} != null && {{get {f}() {{return source.{f};}}}})",
    ],
)
def test_spread_operations_and_variant_objects_are_excluded(expression: str) -> None:
    entries = ",".join(expression.format(f=f) for f in "abc")
    assert _count(f"function f(source) {{ return {{{entries}}}; }}", Language.TYPESCRIPT) == 0


def test_named_constructions_have_independent_destinations() -> None:
    entries = ",".join(f"...(source.{f} != null && {{{f}:source.{f}}})" for f in "ab")
    code = f"function f(source) {{ const first = {{{entries}}}; const second = {{{entries}}}; }}"
    assert _count(code, Language.TYPESCRIPT) == 0


def test_static_receiver_paths_and_comments_keep_identity() -> None:
    body = "\n".join(
        f"if ((source.inner).{f} !== undefined) target.inner.{f} = source['inner'].{f};"
        for f in "abc"
    )
    assert _count(f"function f(source,target) {{{body}}}", Language.TYPESCRIPT) == 1


def test_module_level_execution_is_a_projection_region() -> None:
    code = "const source = getSource(); const target = {};\n" + "\n".join(
        f"if (source.{f} !== undefined) target.{f} = source.{f};" for f in "abc"
    )
    assert _count(code, Language.TYPESCRIPT) == 1


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_shadowed_undefined_destructuring_and_catch(language: Language) -> None:
    body = "\n".join(f"if (s.{f} !== undefined) t.{f} = s.{f};" for f in "abc")
    code = f"function f(s,t,{{undefined}}) {{ {body} }}"
    assert _count(code, language) == 0
    code = f"function f(s,t) {{try {{run();}} catch(undefined) {{ {body} }} }}"
    assert _count(code, language) == 0


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_shadowed_undefined_retains_parameter_reads(language: Language) -> None:
    source = Source("sample", b"export function f(undefined) { return undefined; }", language)
    assert not any(f.rule == "unused.parameter" for f in check(source, Policy()))


def test_catch_binding_does_not_escape_its_scope() -> None:
    body = "\n".join(f"if (s.{f} !== undefined) t.{f} = s.{f};" for f in "abc")
    code = f"function f(s,t) {{try {{run();}} catch(undefined) {{ {body} }} {body} }}"
    assert _count(code, Language.TYPESCRIPT) == 1


@pytest.mark.parametrize(
    "declaration", ["if (ready) {var undefined = 1;}", "{var undefined;}", "{var {undefined} = t;}"]
)
def test_function_scoped_var_shadows_undefined_outside_its_block(declaration: str) -> None:
    body = "\n".join(f"if (s.{f} !== undefined) t.{f} = s.{f};" for f in "abc")
    code = f"function f(s,t) {{ {declaration} {body} }}"
    assert _count(code, Language.TYPESCRIPT) == 0
    nested = f"function f(s,t) {{ {declaration} function inner() {{ {body} }} }}"
    assert _count(nested, Language.TYPESCRIPT) == 0


def test_python_triple_quoted_keys_do_not_alias_different_plain_keys() -> None:
    triple = '"' * 3
    body = "\n".join(
        f' if s[{triple}{f}{triple}] is not None: t.{f} = s[\'""{f}""\']' for f in "abc"
    )
    assert _count(f"def project(s:S,t:T)->None:\n{body}\n", Language.PYTHON) == 0
