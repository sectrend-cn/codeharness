"""Cross-language approvals retain exact scope and serialization-flow checks."""

import pytest

from code_harness.diagnostics import Finding
from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source

_POLICY = Policy.model_validate_json("""{
  "checkers": {"type.broad": {"encoding": {
    "encoders": ["codec.encode", "codec.Encode", "test.Codec.encode"],
    "decoders": ["codec.decode", "codec.Decode", "test.Codec.decode"],
    "instance_outputs": [
      {"path": "sample", "class_name": "Cli", "member": "out", "arguments": [0]}
    ]
  }}}
}""")


def _findings(
    code: str,
    language: Language,
    policy: Policy = _POLICY,
    path: str = "sample",
) -> tuple[Finding, ...]:
    return tuple(
        finding
        for finding in check(Source(path, code.encode(), language), policy)
        if finding.rule == "type.broad" and "erases their contract" in finding.message
    )


@pytest.mark.parametrize("receiver", ["self", "me"])
@pytest.mark.parametrize(
    "body",
    [
        "{r}.out(json.dumps(value))",
        "{r}.out(json.dumps(value) if flag else 'text')",
        "{r}.out('text' if flag else json.dumps(value))",
        "text = json.dumps(value)\n        {r}.out(text)",
        "text = json.dumps(value)\n        copy = text\n        {r}.out(copy)",
        "def nested():\n            {r}.out(json.dumps(value))\n        nested()",
    ],
)
def test_python_instance_parameters_and_closures(receiver: str, body: str) -> None:
    code = f"""import json
class Cli:
    def __init__({receiver}, sink):
        {receiver}.out = sink
    def run({receiver}, value):
        {body.format(r=receiver)}
"""
    assert _findings(code, Language.PYTHON) == ()
    assert len(_findings(code, Language.PYTHON, Policy())) == 1
    assert len(_findings(code, Language.PYTHON, path="other")) == 1


@pytest.mark.parametrize(
    "body",
    [
        "self.out('topic', json.dumps(value))",
        "self.out(*items, json.dumps(value))",
        "self.out(line=json.dumps(value))",
        "self.out(json.loads(json.dumps(value)))",
        "self.out(transform(json.dumps(value)))",
        "text = json.dumps(value)\n        self.out(text)\n        consume(text)",
        "text = json.dumps(value)\n        self.out(text)\n        json.loads(text)",
        "self.out('a' if json.dumps(value) else 'b')",
        "other.out(json.dumps(value))",
        "alias = self\n        alias.out(json.dumps(value))",
        "self = other\n        self.out(json.dumps(value))",
        "def nested(self):\n            self.out(json.dumps(value))",
        "def nested():\n            self = other\n            self.out(json.dumps(value))",
    ],
)
def test_python_internal_and_ambiguous_uses_remain_checked(body: str) -> None:
    code = "import json\nclass Cli:\n    out: Callable\n    def run(self, value):\n        " + body
    assert len(_findings(code, Language.PYTHON)) == 1


@pytest.mark.parametrize("decorator", ["staticmethod", "classmethod", "custom"])
def test_python_decorated_methods_do_not_establish_instance_ownership(decorator: str) -> None:
    code = f"""import json
class Cli:
    out: Callable
    @{decorator}
    def run(self, value):
        self.out(json.dumps(value))
"""
    assert len(_findings(code, Language.PYTHON)) == 1


@pytest.mark.parametrize(
    "declaration",
    ["out: Callable", "def out(self, text):\n        print(text)"],
)
def test_python_direct_callback_declarations_and_methods(declaration: str) -> None:
    code = "import json\nclass Cli:\n    " + declaration
    code += "\n    def run(self):\n        self.out(json.dumps(1))"
    assert _findings(code, Language.PYTHON) == ()


@pytest.mark.parametrize(
    "body",
    [
        "c.out(data)",
        "copy := data; c.out(copy)",
        "c.out(data); c.out(data)",
        "func() { c.out(data) }()",
    ],
)
def test_go_tracks_json_payload_separately_from_error(body: str) -> None:
    code = (
        """package main
import "encoding/json"
type Cli struct { out func([]byte) }
func (c *Cli) run(value Value) {
    data, err := json.Marshal(value)
    if err != nil { report(err); return }
    """
        + body
        + "\n}"
    )
    assert _findings(code, Language.GO) == ()
    assert len(_findings(code, Language.GO, Policy())) == 1
    assert len(_findings(code, Language.GO, path="other")) == 1


@pytest.mark.parametrize(
    "body",
    [
        "c.out(data); consume(data)",
        "c.out(data); json.Unmarshal(data, &result)",
        "c.out(transform(data))",
        "other.out(data)",
        "alias := c; alias.out(data)",
        "c = other; c.out(data)",
        "c.out(err); consume(data)",
        "c.out(err)",
        "c.out(label, data)",
        "func(c *Other) { c.out(data) }(other)",
        "data = replacement; c.out(data)",
    ],
)
def test_go_internal_payload_uses_are_not_hidden_by_output(body: str) -> None:
    code = (
        """package main
import "encoding/json"
type Cli struct { out func([]byte) }
func (c *Cli) run(value Value) {
    data, err := json.Marshal(value)
    """
        + body
        + "\n}"
    )
    assert len(_findings(code, Language.GO)) == 1


@pytest.mark.parametrize("receiver", ["c Cli", "c *Cli"])
def test_go_direct_receiver_methods_and_configured_encoders(receiver: str) -> None:
    code = (
        """package main
import "codec"
type Cli struct {}
func (c Cli) out(text string) { sink(text) }
func ("""
        + receiver
        + """) run(value Value) { c.out(codec.Encode(value)) }
"""
    )
    assert _findings(code, Language.GO) == ()


@pytest.mark.parametrize(
    "body",
    [
        "this.out.accept(codec.toJson(value));",
        'this.out.accept(flag ? codec.toJson(value) : "text");',
        'this.out.accept(flag ? "text" : codec.toJson(value));',
        "String text = codec.toJson(value); this.out.accept(text);",
        "String text = codec.toJson(value); String copy = text; this.out.accept(copy);",
        "Runnable nested = () -> this.out.accept(codec.toJson(value));",
    ],
)
def test_java_functional_fields_and_conditional_output(body: str) -> None:
    code = (
        """import com.google.gson.Gson;
import java.util.function.Consumer;
class Cli {
    Gson codec;
    Consumer<String> out;
    void run(Value value) { """
        + body
        + " } }"
    )
    assert _findings(code, Language.JAVA) == ()
    assert len(_findings(code, Language.JAVA, Policy())) == 1
    assert len(_findings(code, Language.JAVA, path="other")) == 1


@pytest.mark.parametrize(
    "body",
    [
        'this.out.accept("topic", codec.toJson(value));',
        "this.out.accept(codec.fromJson(codec.toJson(value), Value.class));",
        "this.out.accept(transform(codec.toJson(value)));",
        "String text = codec.toJson(value); this.out.accept(text); consume(text);",
        "String text = codec.toJson(value); this.out.accept(text); "
        "codec.fromJson(text, Value.class);",
        "other.out.accept(codec.toJson(value));",
        "Consumer<String> alias = this.out; alias.accept(codec.toJson(value));",
        'this.out.accept(codec.toJson(value) != null ? "a" : "b");',
        "Runnable nested = new Runnable() { public void run() { "
        "this.out.accept(codec.toJson(value)); } };",
    ],
)
def test_java_internal_or_unproved_output_uses_remain_checked(body: str) -> None:
    code = (
        """import com.google.gson.Gson;
import java.util.function.Consumer;
class Cli {
    Gson codec;
    Consumer<String> out;
    void run(Value value) { """
        + body
        + " } }"
    )
    assert len(_findings(code, Language.JAVA)) == 1


def test_java_direct_instance_method_and_configured_static_codec() -> None:
    code = """import test.Codec;
class Cli {
    void out(String text) { sink(text); }
    void run(Value value) { this.out(Codec.encode(value)); }
}"""
    assert _findings(code, Language.JAVA) == ()


@pytest.mark.parametrize("method", ["writeValueAsString", "writeValueAsBytes"])
def test_java_jackson_typed_receiver(method: str) -> None:
    code = (
        """import com.fasterxml.jackson.databind.ObjectMapper;
class Cli {
    ObjectMapper codec;
    void out(String text) { sink(text); }
    void run(Value value) { this.out(codec."""
        + method
        + "(value)); } }"
    )
    assert _findings(code, Language.JAVA) == ()
    assert len(_findings(code, Language.JAVA, Policy())) == 1


def test_gson_streaming_overload_is_not_mistaken_for_serialized_return() -> None:
    code = "import com.google.gson.Gson; class Cli { void run(Gson codec) { "
    code += "codec.toJson(value, writer); } }"
    assert _findings(code, Language.JAVA, Policy()) == ()


@pytest.mark.parametrize(
    "declaration",
    [
        "out: Callable\n    out: Callable",
        "def out(self, text):\n        pass\n    def out(self, text):\n        pass",
        "@property\n    def out(self):\n        return sink",
        "pass",
    ],
)
def test_python_missing_duplicate_or_descriptor_members(declaration: str) -> None:
    code = "import json\nclass Cli:\n    " + declaration
    code += "\n    def run(self):\n        self.out(json.dumps(1))"
    assert len(_findings(code, Language.PYTHON)) == 1


@pytest.mark.parametrize(
    "declaration",
    [
        "type Cli struct { nested struct { out func([]byte) } }",
        "type Base struct { out func([]byte) }; type Cli struct { Base }",
        "type Cli struct { out func([]byte); out func([]byte) }",
        "type Cli struct {}; type Cli struct { out func([]byte) }",
        "type Cli struct { out string }",
        "type Cli struct { out, out func([]byte) }",
        "type Cli struct {}",
    ],
)
def test_go_missing_promoted_or_ambiguous_members(declaration: str) -> None:
    code = 'package main\nimport "encoding/json"\n' + declaration
    code += "\nfunc (c Cli) run() { data, err := json.Marshal(value); c.out(data); report(err) }"
    assert len(_findings(code, Language.GO)) == 1


@pytest.mark.parametrize(
    "body",
    [
        "data, err := json.Marshal(value); os.Stdout.Write(data); report(err)",
        "data, err := json.Marshal(value); os.Stderr.Write(data); report(err)",
        "data, err := json.Marshal(value); os.WriteFile(path, data, mode); report(err)",
        "data, err := json.Marshal(value); fmt.Println(data); report(err)",
        "encode := json.Marshal; data, err := encode(value); c.out(data); report(err)",
        "data, err := json.MarshalIndent(value, prefix, indent); c.out(data); report(err)",
        "data, _ := json.Marshal(value); c.out(data)",
    ],
)
def test_go_native_outputs_and_serializer_aliases(body: str) -> None:
    code = 'package main\nimport "encoding/json"\nimport "os"\nimport "fmt"\n'
    code += "type Cli struct { out func([]byte) }; func (c Cli) run() { " + body + " }"
    assert _findings(code, Language.GO) == ()


@pytest.mark.parametrize(
    "body",
    [
        "data, err := json.Marshal(value); os.WriteFile(data, payload, mode); report(err)",
        "data, err := json.Marshal(value); consume(data); report(err)",
        "data, err := json.Marshal(value); decode := json.Unmarshal; decode(data, &result)",
        "c.out(json.Marshal(value))",
    ],
)
def test_go_unproven_payloads_do_not_establish_output(body: str) -> None:
    code = 'package main\nimport "encoding/json"\nimport "os"\n'
    code += "type Cli struct { out func([]byte) }; func (c Cli) run() { " + body + " }"
    assert len(_findings(code, Language.GO)) == 1


@pytest.mark.parametrize(
    "declaration",
    [
        "static Consumer<String> out;",
        "CustomConsumer out;",
        "Consumer<String> out; Consumer<String> out;",
        "Consumer<String> out, out;",
        "",
    ],
)
def test_java_only_a_unique_instance_consumer_field_is_approved(declaration: str) -> None:
    code = "import com.google.gson.Gson; import java.util.function.Consumer; class Cli { "
    code += declaration + " void run(Gson codec) { this.out.accept(codec.toJson(value)); } }"
    assert len(_findings(code, Language.JAVA)) == 1


@pytest.mark.parametrize(
    "declaration",
    [
        "static void out(String text) {}",
        "void out(String text) {} void out(String text, int other) {}",
        "",
    ],
)
def test_java_static_or_overloaded_methods_are_not_approved(declaration: str) -> None:
    code = "import com.google.gson.Gson; class Cli { " + declaration
    code += " void run(Gson codec) { this.out(codec.toJson(value)); } }"
    assert len(_findings(code, Language.JAVA)) == 1


@pytest.mark.parametrize(
    "body",
    [
        "System.out.println(codec.toJson(value));",
        "System.err.print(codec.toJson(value));",
        "System.out.println(flag ? codec.toJson(value) : text);",
        "this.out(new Gson().toJson(value));",
    ],
)
def test_java_existing_terminal_apis_and_constructor_receivers(body: str) -> None:
    code = "import com.google.gson.Gson; class Cli { void out(String text) {} "
    code += "void run(Gson codec) { " + body + " } }"
    assert _findings(code, Language.JAVA) == ()


def test_java_static_context_and_inherited_members_are_not_approved() -> None:
    code = "import com.google.gson.Gson; class Base { void out(String text) {} } "
    code += "class Cli extends Base { static void run(Gson codec) { this.out(codec.toJson(v)); } }"
    assert len(_findings(code, Language.JAVA)) == 1


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "import json\nclass Other:\n    out: Callable\n"
            "    def run(self):\n        self.out(json.dumps(1))",
        ),
        (
            Language.GO,
            'package main\nimport "encoding/json"\ntype Other struct { out func([]byte) }\n'
            "func (c Other) run() { data, err := json.Marshal(value); c.out(data); report(err) }",
        ),
        (
            Language.JAVA,
            "import com.google.gson.Gson; class Other { void out(String text) {} "
            "void run(Gson codec) { this.out(codec.toJson(value)); } }",
        ),
    ],
)
def test_other_class_or_type_does_not_inherit_approval(language: Language, code: str) -> None:
    assert len(_findings(code, language)) == 1


@pytest.mark.parametrize("parameter", ["*self", "**self"])
def test_python_variadic_parameter_is_not_an_instance_receiver(parameter: str) -> None:
    code = "import json\nclass Cli:\n    out: Callable\n    def run(" + parameter + "):\n"
    code += "        self.out(json.dumps(1))"
    assert len(_findings(code, Language.PYTHON)) == 1


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        (
            Language.GO,
            'package main\nimport "codec"\nimport "transport"\n'
            'func run() { transport.Publish("topic", codec.Encode(value)) }',
            0,
        ),
        (
            Language.GO,
            'package main\nimport "codec"\nimport "transport"\n'
            'func run() { transport.Publish(codec.Encode(value), "topic") }',
            1,
        ),
        (
            Language.GO,
            'package main\nimport "codec"\nimport "transport"\n'
            'func run() { transport.Publish("topic", codec.Decode(codec.Encode(value))) }',
            1,
        ),
        (
            Language.JAVA,
            "import test.Codec; import test.Transport; class Cli { "
            'void run() { Transport.publish("topic", Codec.encode(value)); } }',
            0,
        ),
        (
            Language.JAVA,
            "import test.Codec; import test.Transport; class Cli { "
            'void run() { Transport.publish(Codec.encode(value), "topic"); } }',
            1,
        ),
        (
            Language.JAVA,
            "import test.Codec; import test.Transport; class Cli { "
            'void run() { Transport.publish("topic", Codec.decode(Codec.encode(value))); } }',
            1,
        ),
    ],
)
def test_go_java_configured_output_positions_and_decoders(
    language: Language,
    code: str,
    expected: int,
) -> None:
    policy = Policy.model_validate_json("""{
      "checkers": {"type.broad": {"encoding": {
        "encoders": ["codec.Encode", "test.Codec.encode"],
        "decoders": ["codec.Decode", "test.Codec.decode"],
        "outputs": [
          {"call": "transport.Publish", "arguments": [1]},
          {"call": "test.Transport.publish", "arguments": [1]}
        ]
      }}}
    }""")
    assert len(_findings(code, language, policy)) == expected


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.GO,
            'package main\nimport "custom/json"\n'
            "func run() { data, err := json.Marshal(value); consume(data); report(err) }",
        ),
        (
            Language.GO,
            'package main\nimport "encoding/json"\n'
            "func run(json Codec) { data, err := json.Marshal(value); consume(data); report(err) }",
        ),
        (
            Language.JAVA,
            "import custom.Gson; class Cli { void run(Gson codec) { "
            "String text = codec.toJson(value); consume(text); } }",
        ),
    ],
)
def test_unproved_serializer_names_do_not_invent_library_identity(
    language: Language,
    code: str,
) -> None:
    assert _findings(code, language) == ()
