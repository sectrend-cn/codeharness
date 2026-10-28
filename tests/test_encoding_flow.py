"""Exercise shared alias and output reasoning through real registered JS grammars."""

import pytest

from code_harness.diagnostics import Finding
from code_harness.engine import check
from code_harness.policy.models import BroadTypeOptions, Checkers, Policy
from code_harness.source import Language, Source

_DEFAULT_POLICY = Policy()


@pytest.fixture(params=[Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def dialect(request: pytest.FixtureRequest) -> Language:
    value = request.param
    if not isinstance(value, Language):
        raise TypeError("Expected a registered language identity")
    return value


def _broad(code: str, language: Language, policy: Policy = _DEFAULT_POLICY) -> tuple[Finding, ...]:
    return tuple(
        f
        for f in check(Source("sample", code.encode(), language), policy)
        if f.rule == "type.broad"
    )


@pytest.mark.parametrize(
    "code",
    [
        "const body = JSON.stringify({count: 1});",
        "const encode = JSON.stringify; const body = encode({count: 1});",
        "const encode = JSON.stringify; const copy = encode; const body = copy({count: 1});",
        "const codec = JSON; const body = codec.stringify({count: 1});",
        "const encode = (JSON.stringify); const body = encode({count: 1});",
        "function encode(value) { return JSON.stringify(value); }",
        "const result = JSON.parse(JSON.stringify({count: 1}));",
        "const encode = JSON.stringify; const decode = JSON.parse; "
        "const result = decode(encode({}));",
        "const body = JSON.stringify({}); console.log(body); consume(body);",
        "const body = JSON.stringify({}); const copy = body; const result = JSON.parse(copy);",
        "const body = JSON.stringify({}); console.log(body); JSON.parse(body);",
        "let body = JSON.stringify({}); body = 'replacement'; console.log(body);",
        "const state = {body: JSON.stringify({})}; consume(state);",
        "sink.write(JSON.stringify({}));",
        "function run(console) { console.log(JSON.stringify({})); }",
        "const console = custom; console.log(JSON.stringify({}));",
        "import * as fs from 'custom'; fs.writeFileSync('out', JSON.stringify({}));",
        "import * as fs from 'node:fs'; fs.writeFileSync(JSON.stringify({}), 'payload');",
    ],
)
def test_internal_encoding_and_round_trips_are_reported(dialect: Language, code: str) -> None:
    findings = _broad(code, dialect)
    assert len(findings) == 1
    assert "JSON.stringify" in findings[0].message


@pytest.mark.parametrize(
    "code",
    [
        "console.log(JSON.stringify({count: 1}));",
        "const encode = JSON.stringify; console.log(encode({count: 1}));",
        "const codec = JSON; const encode = codec.stringify; console.error(encode({}));",
        "const body = JSON.stringify({}); const copy = body; console.log(copy);",
        "const body = JSON.stringify({}); console.log(body); console.error(body);",
        "process.stdout.write(JSON.stringify({}));",
        "import * as fs from 'node:fs'; fs.writeFileSync('out', JSON.stringify({}));",
        "import { writeFileSync as write } from 'fs'; write('out', JSON.stringify({}));",
        "import { writeFile } from 'node:fs/promises'; writeFile('out', JSON.stringify({}));",
        "const JSON = codec; const body = JSON.stringify({});",
        "function run(JSON) { return JSON.stringify({}); }",
        "const left = right; const right = left; const result = left({});",
        "function run(encode) { return encode({}); }",
        "const encode = JSON.stringify; function run(encode) { return encode({}); }",
    ],
)
def test_output_and_shadowing_share_the_alias_engine(dialect: Language, code: str) -> None:
    assert _broad(code, dialect) == ()


@pytest.mark.parametrize(
    "body",
    [
        "vendor.send(JSON.stringify({}));",
        "const encode = JSON.stringify; vendor.send(encode({}));",
        "const body = JSON.stringify({}); vendor.send(body);",
        "const body = JSON.stringify({}); const copy = body; vendor.send(copy);",
        "vendor.send({body: JSON.stringify({})});",
        "vendor.send([JSON.stringify({})]);",
        "function callback() { return JSON.stringify({}); } vendor.register(callback);",
    ],
)
def test_configured_library_inputs_reuse_generalized_flow(dialect: Language, body: str) -> None:
    code = "import * as vendor from 'vendor'; " + body
    assert len(_broad(code, dialect)) == 1
    assert _broad(code, dialect, Policy(third_party_modules=("vendor",))) == ()


@pytest.mark.parametrize(
    "body",
    [
        "const body = JSON.stringify({}); vendor.send(body); consume(body);",
        "vendor.send(transform(JSON.stringify({})));",
        "const decode = JSON.parse; vendor.send(decode(JSON.stringify({})));",
        "const body = JSON.stringify({}); vendor.send(body); JSON.parse(body);",
    ],
)
def test_library_use_does_not_hide_internal_consumers(dialect: Language, body: str) -> None:
    code = "import * as vendor from 'vendor'; " + body
    assert len(_broad(code, dialect, Policy(third_party_modules=("vendor",)))) == 1


def test_broad_switch_also_controls_generalized_encoding(dialect: Language) -> None:
    policy = Policy(checkers=Checkers(type_broad=BroadTypeOptions(enabled=False)))
    assert _broad("const body = JSON.stringify({});", dialect, policy) == ()
