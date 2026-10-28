"""Scoped output approvals preserve owner, payload and all-consumer boundaries."""

import pytest
from pydantic import ValidationError

from code_harness.diagnostics import Finding
from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source

_POLICY = Policy.model_validate_json("""{
  "checkers": {"type.broad": {"encoding": {"instance_outputs": [
    {"path": "src/command.ts", "class_name": "Cli", "member": "out", "arguments": [0]}
  ]}}}
}""")


def _findings(
    code: str,
    language: Language = Language.TYPESCRIPT,
    path: str = "src/command.ts",
    policy: Policy = _POLICY,
) -> tuple[Finding, ...]:
    return tuple(
        finding
        for finding in check(Source(path, code.encode(), language), policy)
        if finding.rule == "type.broad"
    )


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
@pytest.mark.parametrize(
    "body",
    [
        "this.out(JSON.stringify({}));",
        "this.out(/* payload */ (JSON.stringify({})));",
        "this.out(flag ? JSON.stringify({}) : 'text');",
        "this.out(flag ? 'text' : JSON.stringify({}));",
        "this.out(flag ? (other ? JSON.stringify({}) : 'a') : 'b');",
        "const text = JSON.stringify({}); this.out(text);",
        "const text = JSON.stringify({}); const copy = text; this.out(copy);",
        "const text = flag ? JSON.stringify({}) : 'text'; this.out(text);",
        "const text = JSON.stringify({}); this.out(text); this.out(text);",
        "const run = () => this.out(JSON.stringify({})); run();",
        "const encode = JSON.stringify; this.out(encode({}));",
    ],
)
def test_direct_and_forwarded_instance_outputs(language: Language, body: str) -> None:
    code = "class Cli { out = sink; run() { " + body + " } }"
    assert _findings(code, language) == ()
    assert len(_findings(code, language, policy=Policy())) == 1


@pytest.mark.parametrize(
    "declaration",
    [
        "private readonly out: (line: string) => void;",
        "out(line: string): void { sink(line); }",
        "out = (line: string) => sink(line);",
    ],
)
def test_function_valued_fields_and_methods(declaration: str) -> None:
    code = "class Cli { " + declaration + " run() { this.out(JSON.stringify({})); } }"
    assert _findings(code) == ()


@pytest.mark.parametrize(
    "body",
    [
        "this.out('label', JSON.stringify({}));",
        "this.out(...args, JSON.stringify({}));",
        "consume(JSON.stringify({}));",
        "this.out(transform(JSON.stringify({})));",
        "this.out(JSON.parse(JSON.stringify({})));",
        "const text = JSON.stringify({}); this.out(text); consume(text);",
        "const text = JSON.stringify({}); this.out(text); JSON.parse(text);",
        "const text = JSON.stringify({}); const copy = text; this.out(copy); consume(copy);",
        "let text = JSON.stringify({}); text = 'other'; this.out(text);",
        "this.out(JSON.stringify({}) ? 'a' : 'b');",
        "consume(flag ? JSON.stringify({}) : 'text');",
        "const text = flag ? JSON.stringify({}) : 'text'; this.out(text); consume(text);",
        "this.out(flag ? JSON.parse(JSON.stringify({})) : 'text');",
        "const that = this; that.out(JSON.stringify({}));",
        "const emit = this.out; emit(JSON.stringify({}));",
        "this['out'](JSON.stringify({}));",
        "this.out.call(this, JSON.stringify({}));",
        "other.out(JSON.stringify({}));",
        "function nested() { this.out(JSON.stringify({})); }",
        "const nested = function () { this.out(JSON.stringify({})); };",
        "const nested = function* () { this.out(JSON.stringify({})); };",
        "const nested = { run() { this.out(JSON.stringify({})); } };",
        "class Other { out = sink; run() { this.out(JSON.stringify({})); } }",
        "class Other { run = () => this.out(JSON.stringify({})); }",
    ],
)
def test_unproved_receivers_and_internal_flows_remain_findings(body: str) -> None:
    code = "class Cli { out = sink; run() { " + body + " } }"
    assert len(_findings(code)) == 1


@pytest.mark.parametrize(
    "code",
    [
        "class Other { out = sink; run() { this.out(JSON.stringify({})); } }",
        "class Cli { static out = sink; static run() { this.out(JSON.stringify({})); } }",
        "class Cli { out = sink; static run() { this.out(JSON.stringify({})); } }",
        "class Cli { static out = sink; run() { this.out(JSON.stringify({})); } }",
        "class Cli { out = sink; static { this.out(JSON.stringify({})); } }",
        "class Cli { out = sink; static run = () => this.out(JSON.stringify({})); }",
        "class Cli { out = sink; run = function () { this.out(JSON.stringify({})); }; }",
        "class Cli { get out() { return sink; } run() { this.out(JSON.stringify({})); } }",
        "class Cli { run() { this.out(JSON.stringify({})); } }",
        "class Base { out = sink; } class Cli extends Base { "
        "run() { this.out(JSON.stringify({})); } }",
        "class Cli { out = sink; 'out' = other; run() { this.out(JSON.stringify({})); } }",
        "class Cli { out = sink; [key] = other; run() { this.out(JSON.stringify({})); } }",
        "class Cli { out = sink; out = other; run() { this.out(JSON.stringify({})); } }",
        "class Cli { out = sink; } function wrap() { class Cli { out = sink; "
        "run() { this.out(JSON.stringify({})); } } }",
        "const Cli = class { out = sink; run() { this.out(JSON.stringify({})); } };",
        "class Cli { out = sink; } this.out(JSON.stringify({}));",
        "class Cli { out = sink; } class Other extends Cli { "
        "run() { this.out(JSON.stringify({})); } }",
    ],
)
@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_unmatched_or_ambiguous_declarations_fail_closed(code: str, language: Language) -> None:
    assert len(_findings(code, language)) == 1


def test_same_named_class_in_another_file_is_not_approved() -> None:
    code = "class Cli { out = sink; run() { this.out(JSON.stringify({})); } }"
    assert len(_findings(code, path="src/other.ts")) == 1
    assert len(_findings(code, path="other/src/command.ts")) == 1
    assert len(_findings(code, path="SRC/command.ts")) == 1


def test_only_the_selected_call_and_payload_change() -> None:
    code = """class Cli {
        out = sink;
        err = sink;
        run(value: unknown) {
            this.out(JSON.stringify({}), JSON.stringify({}));
            this.err(JSON.stringify({}));
        }
    }"""
    before = _findings(code, policy=Policy())
    after = _findings(code)
    removed = tuple(finding for finding in before if finding not in after)
    assert len(before) == 4
    assert len(after) == 3
    assert len(removed) == 1
    assert (removed[0].line, removed[0].column) == (5, 22)


def test_field_arrow_keeps_lexical_this() -> None:
    code = "class Cli { out = sink; run = () => this.out(JSON.stringify({})); }"
    assert _findings(code) == ()


def test_python_member_without_a_declaration_is_not_approved() -> None:
    code = "import json\nclass Cli:\n    def run(self):\n        self.out(json.dumps({}))"
    assert len(_findings(code, language=Language.PYTHON)) == 1


@pytest.mark.parametrize(
    "declaration",
    [
        "{}",
        '{"path":"src/command.ts","class_name":"Cli","member":"out"}',
        '{"path":"src/command.ts","class_name":"Cli","member":"out","arguments":[]}',
        '{"path":"src/command.ts","class_name":"Cli","member":"out","arguments":[-1]}',
        '{"path":"src/command.ts","class_name":"Cli","member":"out","arguments":[true]}',
        '{"path":"src/command.ts","class_name":"Cli","member":"out","arguments":["0"]}',
        '{"path":"src/command.ts","class_name":"Cli","member":"out","arguments":[0.5]}',
        '{"path":"src/command.ts","class_name":"Cli","member":"out","arguments":[0],"keywords":["x"]}',
        '{"path":"src/command.ts","class_name":"","member":"out","arguments":[0]}',
        '{"path":"src/command.ts","class_name":"*","member":"out","arguments":[0]}',
        '{"path":"src/command.ts","class_name":"Cli","member":"this.out","arguments":[0]}',
        '{"path":"src/command.ts","class_name":"Cli","member":"out*","arguments":[0]}',
        '{"path":"src/*.ts","class_name":"Cli","member":"out","arguments":[0]}',
        '{"path":"/src/command.ts","class_name":"Cli","member":"out","arguments":[0]}',
        '{"path":"./src/command.ts","class_name":"Cli","member":"out","arguments":[0]}',
        '{"path":"src/../command.ts","class_name":"Cli","member":"out","arguments":[0]}',
        '{"path":"src//command.ts","class_name":"Cli","member":"out","arguments":[0]}',
        '{"path":"src/command.ts/","class_name":"Cli","member":"out","arguments":[0]}',
        '{"path":"","class_name":"Cli","member":"out","arguments":[0]}',
    ],
)
def test_invalid_instance_declarations_are_rejected(declaration: str) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate_json(
            '{"checkers":{"type.broad":{"encoding":{"instance_outputs":[' + declaration + "]}}}}"
        )


def test_parser_recovery_never_establishes_instance_ownership(
    caplog: pytest.LogCaptureFixture,
) -> None:
    code = "class Cli { out = sink; run() { this.out(JSON.stringify({})); } } const broken = ;"
    assert len(_findings(code)) == 1
    assert "Parser" in caplog.text


def test_private_member_syntax_does_not_match_public_member_selector() -> None:
    code = "class Cli { #out = sink; run() { this.#out(JSON.stringify({})); } }"
    assert len(_findings(code)) == 1


def test_nonzero_payload_positions_are_selected_exactly() -> None:
    policy = Policy.model_validate_json("""{
      "checkers": {"type.broad": {"encoding": {"instance_outputs": [
        {"path": "src/command.ts", "class_name": "Cli", "member": "out", "arguments": [1]}
      ]}}}
    }""")
    code = "class Cli { out = sink; run() { this.out('topic', JSON.stringify({})); } }"
    assert _findings(code, policy=policy) == ()
    assert len(_findings(code)) == 1


def test_unqualified_this_output_configuration_remains_inert() -> None:
    policy = Policy.model_validate_json("""{
      "checkers": {"type.broad": {"encoding": {"outputs": [
        {"call": "this.out", "arguments": [0]}
      ]}}}
    }""")
    code = "class Cli { out = sink; run() { this.out(JSON.stringify({})); } }"
    assert len(_findings(code, policy=policy)) == 1


@pytest.mark.parametrize("language", [Language.TYPESCRIPT, Language.TSX])
def test_explicit_this_parameters_do_not_inherit_lexical_approval(language: Language) -> None:
    code = "class Cli { out = sink; run(this: Other) { this.out(JSON.stringify({})); } }"
    assert len(_findings(code, language)) == 1
