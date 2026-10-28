"""JSON encoding must retain the existing directional third-party exemptions."""

from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import Finding, Report
from code_harness.engine import check
from code_harness.policy.models import BroadTypeOptions, CheckerOptions, Checkers, Policy
from code_harness.source import Language, Source

_DEFAULT_POLICY = Policy()


def _erasure(code: str, policy: Policy = _DEFAULT_POLICY) -> tuple[Finding, ...]:
    return tuple(
        finding
        for finding in check(Source("app.py", code.encode(), Language.PYTHON), policy)
        if finding.rule == "type.broad"
    )


@pytest.mark.parametrize(
    "code",
    [
        "import json\nvalue = json.dumps({'count': 1})\n",
        "import json as codec\nvalue = codec.dumps({'count': 1})\n",
        "from json import dumps\nvalue = dumps({'count': 1})\n",
        "from json import dumps as encode\nvalue = encode({'count': 1})\n",
        "import json\ndef encode(value: dict[str, int]) -> str:\n    return json.dumps(value)\n",
        "import json\nvalue = json.loads(json.dumps({'count': 1}))\n",
    ],
)
def test_internal_json_encoding_is_type_erasure(code: str) -> None:
    findings = _erasure(code)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "json.dumps" in findings[0].message
    assert _erasure(code, Policy(third_party_modules=("json",))) == findings


@pytest.mark.parametrize(
    "body",
    [
        "vendor.send(json.dumps({'count': 1}))\n",
        "vendor.send(body=json.dumps({'count': 1}))\n",
        "vendor.send({'body': json.dumps({'count': 1})})\n",
        "vendor.send([json.dumps({'count': 1})])\n",
        "vendor.send((json.dumps({'count': 1}),))\n",
        "vendor.send((json.dumps({'count': 1})))\n",
        "body = json.dumps({'count': 1})\nvendor.send(body)\n",
        "body: str = json.dumps({'count': 1})\nvendor.send(body=body)\n",
        "body = {'body': json.dumps({'count': 1})}\nvendor.send(body)\n",
        "body = json.dumps({'count': 1})\ncopy = body\nvendor.send(copy)\n",
        "body = json.dumps({'count': 1})\nvendor.send(body)\nvendor.send(body)\n",
        "def callback() -> str:\n    return json.dumps({'count': 1})\nvendor.register(callback)\n",
        "def callback() -> str:\n    body = json.dumps({'count': 1})\n"
        "    return body\nvendor.register(callback)\n",
    ],
)
def test_json_encoding_used_only_as_library_input_is_exempt(body: str) -> None:
    code = "import json\nimport vendor\n" + body
    assert len(_erasure(code)) == 1
    assert _erasure(code, Policy(third_party_modules=("vendor",))) == ()


@pytest.mark.parametrize(
    "body",
    [
        "body = json.dumps({'count': 1})\nvendor.send(body)\nconsume(body)\n",
        "body = json.dumps({'count': 1})\nvendor.send(body)\ncopy = body\nconsume(copy)\n",
        "vendor.send(transform(json.dumps({'count': 1})))\n",
        "body = json.dumps({'count': 1})\nbody = 'replacement'\nvendor.send(body)\n",
        "class Holder:\n    body = json.dumps({'count': 1})\nvendor.send(Holder.body)\n",
        "def callback() -> str:\n    return json.dumps({'count': 1})\n"
        "vendor.register(callback)\ncallback()\n",
        "def encode() -> str:\n    return json.dumps({'count': 1})\nvendor.send(encode())\n",
        "def run(vendor: Client) -> None:\n    vendor.send(json.dumps({'count': 1}))\n",
        "vendor.send({json.dumps({'count': 1}): 'value'})\n",
        "body = json.dumps({'count': 1})\nbody = body\nvendor.send(body)\n",
        "body = json.dumps({'count': 1})\nbody += 'suffix'\nvendor.send(body)\n",
    ],
)
def test_library_use_does_not_exempt_internal_consumers(body: str) -> None:
    code = "import json\nimport vendor\n" + body
    assert len(_erasure(code, Policy(third_party_modules=("vendor",)))) == 1


@pytest.mark.parametrize(
    "code",
    [
        "from vendor import send as deliver\ndeliver(json.dumps({'count': 1}))\n",
        "import vendor as sdk\nsdk.send(json.dumps({'count': 1}))\n",
    ],
)
def test_library_import_aliases_keep_the_boundary(code: str) -> None:
    assert _erasure("import json\n" + code, Policy(third_party_modules=("vendor",))) == ()


def test_third_party_configuration_matches_exact_module() -> None:
    code = "import json\nfrom vendor.client import send\nsend(json.dumps({'count': 1}))\n"
    assert len(_erasure(code, Policy(third_party_modules=("vendor",)))) == 1
    assert _erasure(code, Policy(third_party_modules=("vendor.client",))) == ()


@pytest.mark.parametrize(
    "code",
    [
        "from custom import dumps\nvalue = dumps({'count': 1})\n",
        "import custom as json\nvalue = json.dumps({'count': 1})\n",
        "import json\ndef run(json: Codec) -> str:\n    return json.dumps({'count': 1})\n",
        "from json import dumps\ndef run(dumps: Codec) -> str:\n    return dumps({'count': 1})\n",
        "from json import dumps\ndumps = custom\nvalue = dumps({'count': 1})\n",
        "import json\njson = custom\nvalue = json.dumps({'count': 1})\n",
        "import json\nvalue = json.loads('{}')\n",
        "import json\njson.dump({'count': 1}, stream)\n",
        "text = 'json.dumps(payload)'\n",
    ],
)
def test_other_calls_and_shadowed_imports_are_not_json_dumps(code: str) -> None:
    assert _erasure(code) == ()


def test_broad_type_check_is_independent_of_boundary_switch() -> None:
    code = "import json\nfrom vendor import send\nsend(json.dumps({'count': 1}))\n"
    policy = Policy(
        third_party_modules=("vendor",),
        checkers=Checkers(type_boundary=CheckerOptions(enabled=False)),
    )
    assert _erasure(code, policy) == ()
    assert len(_erasure("import json\nvalue = json.dumps({})\n", policy)) == 1


def test_cli_reports_serialization_and_preserves_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    source = tmp_path / "app.py"
    content = b"import json\nvalue = json.dumps({'count': 1})\n"
    source.write_bytes(content)
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert (finding.rule, finding.path, finding.line, finding.column) == (
        "type.broad",
        "app.py",
        2,
        9,
    )
    assert source.read_bytes() == content


@pytest.mark.parametrize(
    "expression",
    [
        "json.loads((json.dumps({'count': 1})))",
        "json.loads(s=json.dumps({'count': 1}))",
        "json.loads(s=(json.dumps({'count': 1})))",
    ],
)
def test_configured_json_decoder_does_not_exempt_round_trip(expression: str) -> None:
    code = "import json\nvalue = " + expression + "\n"
    assert len(_erasure(code, Policy(third_party_modules=("json",)))) == 1


def test_callback_input_still_requires_typed_ingress() -> None:
    code = (
        "import json\nfrom vendor import register\n"
        "def callback(raw: dict[str, object]) -> str:\n"
        "    return json.dumps(raw)\nregister(callback)\n"
    )
    findings = check(
        Source("app.py", code.encode(), Language.PYTHON),
        Policy(third_party_modules=("vendor",)),
    )
    assert any(finding.rule == "type.boundary" for finding in findings)
    assert not any(finding.rule == "type.broad" for finding in findings)


def test_broad_switch_groups_json_and_markers_preserving_annotation_checks() -> None:
    code = (
        "import json\nfrom typing import Any\n"
        "value: Any = None\nother: object = None\nencoded = json.dumps({'count': 1})\n"
    )
    source = Source("app.py", code.encode(), Language.PYTHON)
    enabled = check(source, Policy())
    broad = [finding for finding in enabled if finding.rule == "type.broad"]
    assert {finding.line for finding in broad} == {3, 5}
    policy = Policy(checkers=Checkers(type_broad=BroadTypeOptions(enabled=False)))
    disabled = check(source, policy)
    assert disabled == tuple(finding for finding in enabled if finding.rule != "type.broad")
    assert {finding.line for finding in disabled if finding.rule == "type.annotation"} == {3, 4}


def test_cli_uses_broad_checker_switch_for_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"type.broad":{"enabled":false}}}'
    )
    (tmp_path / "app.py").write_text("import json\nencoded = json.dumps({'count': 1})\n")
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.findings == ()
    assert report.disabled_checkers == ("type.broad",)


@pytest.mark.parametrize(
    "body",
    [
        "print(json.dumps({'count': 1}))",
        "body = json.dumps({'count': 1})\nprint(body)",
        "body = json.dumps({'count': 1})\ncopy = body\nprint(copy)",
        "import sys\nsys.stdout.write(json.dumps({'count': 1}))",
        "import sys as system\nsystem.stderr.write(json.dumps({'count': 1}))",
        "from pathlib import Path\nPath('out.json').write_text(json.dumps({'count': 1}))",
        "from pathlib import Path as FilePath\noutput = FilePath('out.json')\n"
        "output.write_text(json.dumps({'count': 1}))",
        "with open('out.json', 'w') as stream:\n    stream.write(json.dumps({'count': 1}))",
        "with open('out.json', mode='a') as stream:\n"
        "    print(json.dumps({'count': 1}), file=stream)",
        "import builtins\nbuiltins.print(json.dumps({'count': 1}))",
        "emit = print\nemit(json.dumps({'count': 1}))",
        "import vendor\nbody = json.dumps({'count': 1})\nprint(body)\nvendor.send(body)",
    ],
)
def test_proven_json_output_is_permitted(body: str) -> None:
    assert _erasure("import json\n" + body, Policy(third_party_modules=("vendor",))) == ()


@pytest.mark.parametrize(
    "body",
    [
        "def print(value: str) -> str:\n    return value\nprint(json.dumps({}))",
        "def send(print: Printer) -> None:\n    print(json.dumps({}))",
        "import io\nbuffer = io.StringIO()\nbuffer.write(json.dumps({}))",
        "import io\nprint(json.dumps({}), file=io.StringIO())",
        "sink.write(json.dumps({}))",
        "sink.write_text(json.dumps({}))",
        "def send(open: Opener) -> None:\n    with open('out', 'w') as stream:\n"
        "        stream.write(json.dumps({}))",
        "with open('in.json') as stream:\n    stream.write(json.dumps({}))",
        "with open('out', 'w') as stream:\n    stream = custom\n    stream.write(json.dumps({}))",
        "with open('out', 'w') as stream:\n    with other() as stream:\n"
        "        stream.write(json.dumps({}))",
        "from pathlib import Path\noutput = Path('out')\noutput = custom\n"
        "output.write_text(json.dumps({}))",
        "body = json.dumps({})\nprint(body)\nconsume(body)",
        "body = json.dumps({})\nprint(body)\nvalue = json.loads(body)",
    ],
)
def test_output_names_do_not_exempt_internal_or_unproven_consumers(body: str) -> None:
    assert len(_erasure("import json\n" + body)) == 1


@pytest.mark.parametrize(
    "body",
    [
        "encode = json.dumps\nvalue = encode({})",
        "encode = json.dumps\ncopy = encode\nvalue = copy({})",
        "codec = json\nvalue = codec.dumps({})",
        "from json import dumps\nencode = dumps\nvalue = encode({})",
        "def run() -> str:\n    encode = json.dumps\n    return encode({})",
        "encode = (json.dumps)\nvalue = encode({})",
        "encode = json.dumps\ndecode = json.loads\nvalue = decode(encode({}))",
        "encode = json.dumps\ndecode = json.loads\nbody = encode({})\nvalue = decode(s=(body))",
    ],
)
def test_json_callable_and_module_aliases_preserve_identity(body: str) -> None:
    assert len(_erasure("import json\n" + body, Policy(third_party_modules=("json",)))) == 1


@pytest.mark.parametrize(
    "body",
    [
        "encode = json.dumps\nprint(encode({}))",
        "encode = json.dumps\nimport vendor\nvendor.send(encode({}))",
        "encode = json.dumps\ndef run(encode: Encoder) -> str:\n    return encode({})",
        "encode = custom\nvalue = encode({})",
        "left = right\nright = left\nvalue = left({})",
        "import custom as json\nencode = json.dumps\nvalue = encode({})",
    ],
)
def test_alias_resolution_respects_output_shadowing_and_cycles(body: str) -> None:
    assert _erasure("import json\n" + body, Policy(third_party_modules=("vendor",))) == ()
