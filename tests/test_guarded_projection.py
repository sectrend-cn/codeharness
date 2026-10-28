"""Cross-language behavioral contract for repeated guarded field projections."""

import pytest
from pydantic import ValidationError

from code_harness.diagnostics import Finding
from code_harness.engine import check
from code_harness.plugins.builtins import builtin_analyzers
from code_harness.policy.models import Checkers, Policy
from code_harness.semantics.projection.options import GuardedProjectionOptions
from code_harness.source import Language, Source

_DEFAULT_POLICY = Policy()
_SCRIPT_LANGUAGES = (Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX)


def _findings(
    code: str, language: Language = Language.TYPESCRIPT, policy: Policy = _DEFAULT_POLICY
) -> tuple[Finding, ...]:
    return tuple(
        finding
        for finding in check(Source("projection", code.encode(), language), policy)
        if finding.rule == "structure.guarded_projection"
    )


def _script(statements: str) -> str:
    return f"function project(source, target, other) {{\n{statements}\nreturn target;\n}}"


def _assignments(fields: str = "abc") -> str:
    return "\n".join(
        f"if (source?.{name} !== undefined) target.{name} = source.{name};" for name in fields
    )


@pytest.mark.parametrize("language", _SCRIPT_LANGUAGES)
@pytest.mark.parametrize(
    "template",
    [
        "if (source?.{f} !== undefined) target.{f} = source.{f};",
        "if ((source.{f}) === undefined) {{}} else {{ target.{f} = (source.{f}); }}",
        'if (source["{f}"] != null) target["renamed_{f}"] = source.{f};',
        "if (undefined !== source.{f}) {{ /* guard */ target.{f} = source.{f}; }};",
    ],
)
def test_script_assignment_forms(language: Language, template: str) -> None:
    code = _script("\n/* separator */\n".join(template.format(f=f) for f in "abc"))
    findings = _findings(code, language)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "3 guarded field projections from source into target" in findings[0].message
    assert findings[0].line == 2
    assert "locations 2:1, 4:1, 6:1" in findings[0].message


@pytest.mark.parametrize("language", _SCRIPT_LANGUAGES)
@pytest.mark.parametrize(
    "template",
    [
        "...(source.{f} === undefined ? {{}} : {{{f}: source.{f}}})",
        "...(source.{f} !== undefined ? {{{f}: source.{f}}} : {{}})",
        "...(source.{f} != null && {{{f}: source.{f}}})",
    ],
)
def test_script_spread_forms(language: Language, template: str) -> None:
    code = "function project(source) { return {\n"
    code += ",\n".join(template.format(f=f) for f in "abc") + "}; }"
    findings = _findings(code, language)
    assert len(findings) == 1
    assert "3 guarded field projections from source into returned object" in findings[0].message
    assert findings[0].line == 2


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "def project(source: S, target: T) -> None:\n"
            + "".join(
                f"    if source.{f} is not None:\n        target.{f} = source.{f}\n" for f in "abc"
            ),
        ),
        (
            Language.GO,
            "package p\nfunc Project(source S, target T) {\n"
            + "".join(f"if source.{f} != nil {{ target.{f} = source.{f} }}\n" for f in "ABC")
            + "}",
        ),
        (
            Language.JAVA,
            "class C { void project(S source, T target) {\n"
            + "".join(f"if (source.{f} != null) target.{f} = source.{f};\n" for f in "abc")
            + "}}",
        ),
    ],
)
def test_other_languages_share_threshold_and_evidence(language: Language, code: str) -> None:
    findings = _findings(code, language)
    assert len(findings) == 1
    assert "3 guarded field projections from source into target" in findings[0].message
    assert code.splitlines()[findings[0].line - 1].lstrip().startswith("if")
    assert "presence" in findings[0].message


@pytest.mark.parametrize("literal", ["True", "False", "7", "-7", "'ready'"])
def test_python_inverted_guards_and_literal_equality(literal: str) -> None:
    code = "def project(source: S, target: T) -> None:\n"
    code += "    if source.a is None:\n        pass\n    else:\n        target.a = source.a\n"
    code += f"    if source.b == {literal}:\n        target.b = {literal}\n"
    code += "    if source['c'] is not None:\n        target['c'] = source['c']\n"
    assert len(_findings(code, Language.PYTHON)) == 1


def test_python_conditional_dictionary_unpacking() -> None:
    code = (
        "def project(source: S) -> T:\n    return {\n"
        + ",\n".join(
            f"        **({{'{f}': source.{f}}} if source.{f} is not None else {{}})" for f in "abc"
        )
        + "\n    }\n"
    )
    findings = _findings(code, Language.PYTHON)
    assert len(findings) == 1
    assert "returned object" in findings[0].message


@pytest.mark.parametrize("language", [Language.GO, Language.JAVA])
def test_go_java_inverted_and_literal_guards(language: Language) -> None:
    sources = {
        Language.GO: "package p\nfunc F(s S,t T) { if s.A == nil {} else {t.A=s.A};\n"
        'if s.B == true {t.B=true}; if s.C == "ready" {t.C="ready"} }',
        Language.JAVA: "class C { void f(S s,T t) { if(s.a == null) {} else {t.a=s.a;} "
        "if(s.b == true) t.b=true; if(s.c == 7) t.c=7; }}",
    }
    assert len(_findings(sources[language], language)) == 1


@pytest.mark.parametrize("literal", ["true", "false", "7", "-7", "'ready'"])
def test_script_literal_guard_can_copy_the_established_literal(literal: str) -> None:
    code = _script(
        "\n".join(f"if (source.{f} === {literal}) target.{f} = {literal};" for f in "abc")
    )
    findings = _findings(code)
    assert len(findings) == 1
    assert "equality" in findings[0].message


@pytest.mark.parametrize(
    ("count", "threshold", "expected"), [(2, 3, 0), (3, 3, 1), (2, 2, 1), (3, 4, 0), (4, 4, 1)]
)
def test_inclusive_distinct_field_threshold(count: int, threshold: int, expected: int) -> None:
    policy = Policy(
        checkers=Checkers(guarded_projection=GuardedProjectionOptions(min_fields=threshold))
    )
    assert len(_findings(_script(_assignments("abcd"[:count])), policy=policy)) == expected


@pytest.mark.parametrize("fields", ["aaa", "aab", "aba"])
def test_duplicate_destination_fields_do_not_reach_threshold(fields: str) -> None:
    assert _findings(_script(_assignments(fields))) == ()


@pytest.mark.parametrize(
    "statement",
    [
        "if (source.{f} !== undefined) target.{f} = source.{f} + 1;",
        "if (source.{f} !== undefined) target.{f} = convert(source.{f});",
        "if (source.{f} !== undefined) {{ target.{f} = source.{f}; audit(); }}",
        "if (source.{f} !== undefined) return source.{f};",
        "if (source.{f} !== undefined) throw Error();",
        "if (source.{f}) target.{f} = source.{f};",
        "if (source.{f} !== undefined && ready) target.{f} = source.{f};",
        "if (source[key] !== undefined) target.{f} = source[key];",
        "if (source.{f} !== undefined) target[key] = source.{f};",
        "if (source().{f} !== undefined) target.{f} = source().{f};",
        "if (source.{f} !== undefined) target().{f} = source.{f};",
        "if (source.{f} !== undefined) target.{f} = other.{f};",
        "if (source.{f} !== undefined) target.{f} = source.other;",
        "if (source.{f} === true) target.{f} = false;",
        "if (source.{f} == true) target.{f} = true;",
        "if (source.{f} !== undefined) target.{f} += source.{f};",
        "if (source.{f} !== undefined) target.{f} = source.{f}; else target.{f} = 0;",
        "target.{f} = source.{f} ?? 0;",
    ],
)
def test_script_excludes_operations_and_unproved_predicates(statement: str) -> None:
    assert _findings(_script("\n".join(statement.format(f=f) for f in "abc"))) == ()


@pytest.mark.parametrize(
    "interrupt",
    [
        "audit();",
        "target = other;",
        "source = other;",
        "const x = 1;",
        "if (other.a !== undefined) target.a = other.a;",
        "if (source.a !== undefined) other.a = source.a;",
        "function nested(source, target) {" + _assignments("ab") + "}",
        "for (;;) {" + _assignments("ab") + "}",
        "if (ready) {" + _assignments("ab") + "}",
    ],
)
def test_statement_boundaries_split_clusters(interrupt: str) -> None:
    assert (
        _findings(_script(_assignments("ab") + "\n" + interrupt + "\n" + _assignments("cd"))) == ()
    )


@pytest.mark.parametrize(
    "interrupt",
    ["ordinary: 1", "...other", "...(other.x != null && {x: other.x})", "nested: {}"],
)
def test_object_properties_split_spread_clusters(interrupt: str) -> None:
    entries = [f"...(source.{f} != null && {{{f}:source.{f}}})" for f in "abcd"]
    entries.insert(2, interrupt)
    assert _findings("function f(source,other) { return {" + ",".join(entries) + "}; }") == ()


def test_separate_objects_and_nested_functions_keep_own_clusters() -> None:
    entries = ",".join(f"...(source.{f} != null && {{{f}:source.{f}}})" for f in "abc")
    code = _script(
        _assignments()
        + "\nfunction nested(source,target) {"
        + _assignments()
        + "}\n"
        + f"return {{nested: {{{entries}}}, ...({{unused: 1}}), {entries}}};"
    )
    assert len(_findings(code)) == 4


@pytest.mark.parametrize(
    "declaration", ["const alias = source;", "const first = source; const alias = first;"]
)
def test_const_aliases_share_binding_identity(declaration: str) -> None:
    body = _assignments("a") + "\n" + _assignments("bc").replace("source", "alias")
    assert len(_findings(_script(declaration + "\n" + body))) == 1


@pytest.mark.parametrize(
    "declaration",
    [
        "let alias = source;",
        "var alias = source;",
        "const alias = source; source = other;",
        "const alias = source; alias = other;",
        "const alias = unknown;",
    ],
)
def test_unproved_aliases_do_not_merge_with_source(declaration: str) -> None:
    body = _assignments("a") + "\n" + _assignments("bc").replace("source", "alias")
    assert _findings(_script(declaration + "\n" + body)) == ()


@pytest.mark.parametrize("binding", ["parameter", "const", "let", "var", "function"])
def test_shadowed_undefined_is_not_builtin_presence(binding: str) -> None:
    declarations = {
        "parameter": "function f(source,target,undefined) {",
        "const": "function f(source,target) { const undefined = 0;",
        "let": "function f(source,target) { let undefined = 0;",
        "var": "function f(source,target) { var undefined = 0;",
        "function": "function f(source,target) { function undefined() {}",
    }
    assert _findings(declarations[binding] + _assignments() + "}") == ()


@pytest.mark.parametrize(
    "option",
    [
        '{"min_fields":1}',
        '{"min_fields":true}',
        '{"min_fields":"3"}',
        '{"min_fields":3.0}',
        '{"unknown":3}',
        '{"enabled":0}',
    ],
)
def test_strict_projection_options(option: str) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate_json('{"checkers":{"structure.guarded_projection":' + option + "}}")


def test_disabled_checker_and_all_language_registration() -> None:
    policy = Policy.model_validate_json(
        '{"checkers":{"structure.guarded_projection":{"enabled":false}}}'
    )
    assert _findings(_script(_assignments()), policy=policy) == ()
    assert policy.checkers.disabled_checkers() == {"structure.guarded_projection"}
    assert all(
        "structure.guarded_projection" in analyzer.rule_ids for analyzer in builtin_analyzers()
    )
    assert Policy().checkers.guarded_projection.min_fields == 3


def test_motivating_function_preserves_two_destinations_and_complexity() -> None:
    code = """function responseMetrics(response, start, end, durationMs) {
const usage = response.usage;
const extra: NonNullable<Trace.Metrics["extra"]> = {
    started_at: start, ended_at: end, duration_ms: durationMs
};
if (usage?.cacheExclusiveInputTokens !== undefined) extra.cache_exclusive_input_tokens =
    usage.cacheExclusiveInputTokens;
if (usage?.incomplete === true) extra.usage_incomplete = true;
if (usage?.cacheCreationInputTokens !== undefined) extra.cache_creation_input_tokens =
    usage.cacheCreationInputTokens;
if (usage?.cacheReadInputTokens !== undefined) extra.cache_read_input_tokens =
    usage.cacheReadInputTokens;
if (usage?.reasoningTokens !== undefined) extra.reasoning_tokens = usage.reasoningTokens;
if (usage?.cacheCreation5mInputTokens !== undefined) extra.cache_creation_5m_input_tokens =
    usage.cacheCreation5mInputTokens;
if (usage?.cacheCreation1hInputTokens !== undefined) extra.cache_creation_1h_input_tokens =
    usage.cacheCreation1hInputTokens;
return {
    ...(usage?.inputTokens === undefined ? {} : { prompt_tokens: usage.inputTokens }),
    ...(usage?.outputTokens === undefined ? {} : { completion_tokens: usage.outputTokens }),
    ...(usage?.cachedTokens === undefined ? {} : { cached_tokens: usage.cachedTokens }),
    extra
};
}"""
    code = code.replace(" =\n    usage.", " = usage.")
    source = Source("metrics.ts", code.encode(), Language.TYPESCRIPT)
    findings = check(source, Policy())
    projections = tuple(f for f in findings if f.rule == "structure.guarded_projection")
    assert len(projections) == 2
    assert "7 guarded field projections from usage into extra" in projections[0].message
    assert "3 guarded field projections from usage into returned object" in projections[1].message
    assert (projections[0].line, projections[1].line) == (6, 14)
    assert any(f.rule == "size.complexity" for f in findings)
    assert check(source, Policy()) == findings
