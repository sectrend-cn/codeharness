"""Declaration evidence is tested even where exported methods bypass unused diagnostics."""

import pytest

from code_harness.languages.go import GoLanguage
from code_harness.languages.go.semantic_syntax import GoSemanticSyntax
from code_harness.languages.java import JavaLanguage
from code_harness.languages.java.semantic_syntax import JavaSemanticSyntax
from code_harness.languages.python import PythonLanguage
from code_harness.languages.python.semantic_syntax import PythonSemanticSyntax
from code_harness.languages.typescript import TypeScriptLanguage
from code_harness.languages.typescript.semantic_syntax import TypeScriptSemanticSyntax
from code_harness.policy.models import Policy
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.project import ProjectUsage
from code_harness.source import Language, Source


def _typescript(code: str, path: str) -> SemanticIndex:
    source = Source(path, code.encode(), Language.TYPESCRIPT)
    return SemanticIndex(
        TypeScriptLanguage().parser.parse(source, Policy()), TypeScriptSemanticSyntax()
    )


def test_java_abstract_generic_chain_records_hook_and_super_declarations() -> None:
    source = Source(
        "View.java",
        b"""abstract class Base {
    String render() { return this.hook(); }
    abstract String hook();
}
abstract class Middle<T> extends Base {
    String render() { return super.render(); }
    String hook() { return "used"; }
}
class Leaf extends Middle<String> {}
class Entry { String execute(Base view) { return view.render(); } }
""",
        Language.JAVA,
    )
    index = SemanticIndex(JavaLanguage().parser.parse(source, Policy()), JavaSemanticSyntax())
    project = ProjectUsage((index,))
    project.prepare()
    evidence = project.evidence()
    middle = index.class_scope("Middle")
    base = index.class_scope("Base")
    assert middle is not None and base is not None
    assert [scope.owner for scope in middle.bases] == ["Base"]
    assert middle.symbols["render"].node.id in evidence.contract_reads
    assert middle.symbols["hook"].node.id in evidence.contract_reads
    assert any(read.start_point.row == 5 for read in base.symbols["render"].reads)


def test_go_explicit_composition_keeps_receiver_methods_separate() -> None:
    source = Source(
        "view.go",
        b"""package sample
type Base struct {}
func (b Base) render() int { return 1 }
type Leaf struct { base Base }
func (l Leaf) render() int { return l.base.render() }
type Other struct {}
func (o Other) render() int { return 2 }
func Execute() int { leaf := Leaf{}; return leaf.render() }
""",
        Language.GO,
    )
    index = SemanticIndex(GoLanguage().parser.parse(source, Policy()), GoSemanticSyntax())
    project = ProjectUsage((index,))
    project.prepare()
    base, leaf, other = (index.class_scope(name) for name in ("Base", "Leaf", "Other"))
    assert base is not None and leaf is not None and other is not None
    assert base.symbols["render"].reads
    assert leaf.symbols["render"].reads
    assert not other.symbols["render"].reads
    assert not leaf.bases


def test_imported_abstract_declarations_receive_real_dispatch_evidence() -> None:
    base = _typescript(
        "export abstract class Base {\n"
        " render(): string { return this.hook(); }\n"
        " protected abstract hook(): string;\n}\n",
        "base.ts",
    )
    middle = _typescript(
        'import { Base } from "./base";\n'
        "export abstract class Middle<T> extends Base {\n"
        " render(): string { return super.render(); }\n"
        " protected hook(): string { return 'used'; }\n}\n",
        "middle.ts",
    )
    leaf = _typescript(
        'import { Base } from "./base";\nimport { Middle } from "./middle";\n'
        "class Leaf extends Middle<string> {}\n"
        "function create(): Base { return new Leaf(); }\n"
        "export function run(): string { return create().render(); }\n",
        "leaf.ts",
    )
    project = ProjectUsage((leaf, middle, base))
    project.prepare()
    evidence = project.evidence()
    owner = middle.class_scope("Middle")
    assert owner is not None
    assert [
        (
            owner.symbols[name].node.start_point.row + 1,
            owner.symbols[name].node.id in evidence.contract_reads,
        )
        for name in ("render", "hook")
    ] == [(3, True), (4, True)]
    assert project.evidence() == evidence


@pytest.mark.parametrize("base", ["Missing", "External"])
def test_unresolved_external_base_does_not_create_a_local_edge(base: str) -> None:
    index = _typescript(
        'import { External } from "vendor";\n'
        f"class Child extends {base} {{ run(): number {{ return 1; }} }}\n",
        "child.ts",
    )
    owner = index.class_scope("Child")
    assert owner is not None and owner.bases == []


def test_shadowed_python_super_does_not_read_a_base_method() -> None:
    source = Source(
        "view.py",
        b"from typing import Callable\n"
        b"class Other:\n    def read(self) -> int:\n        return 2\n"
        b"class Base:\n    def read(self) -> int:\n        return 1\n"
        b"class Child(Base):\n"
        b"    def read(self, super: Callable[[], Other]) -> int:\n        return super().read()\n",
        Language.PYTHON,
    )
    index = SemanticIndex(PythonLanguage().parser.parse(source, Policy()), PythonSemanticSyntax())
    project = ProjectUsage((index,))
    project.prepare()
    base = index.class_scope("Base")
    assert base is not None
    assert not base.symbols["read"].reads
    assert base.symbols["read"].node.id not in project.evidence().contract_reads


def test_typescript_implements_uses_only_nominal_contracts() -> None:
    index = _typescript(
        "class Argument {}\n"
        "abstract class Base<T> { abstract read(value: T): string; }\n"
        "abstract class Other {}\n"
        "class Child implements Base<Argument>, Other {\n"
        " read(value: Argument): string { return 'unused'; }\n}\n",
        "view.ts",
    )
    owner = index.class_scope("Child")
    assert owner is not None
    assert [base.owner for base in owner.bases] == ["Base", "Other"]


def test_java_static_hiding_does_not_share_instance_dispatch_or_parameters() -> None:
    source = Source(
        "View.java",
        b"class Base { static int read(int value) { return value; } }\n"
        b"class Child extends Base { static int read(int value) { return 1; } }\n"
        b"class Entry { int run() { return Child.read(1); } }\n",
        Language.JAVA,
    )
    index = SemanticIndex(JavaLanguage().parser.parse(source, Policy()), JavaSemanticSyntax())
    project = ProjectUsage((index,))
    project.prepare()
    base, child = index.class_scope("Base"), index.class_scope("Child")
    assert base is not None and child is not None
    assert not base.static_symbols["read"].reads
    assert child.static_symbols["read"].reads
    parameters = [symbol for symbol in index.symbols() if symbol.kind == "parameter"]
    assert parameters[0].reads
    assert not parameters[1].reads
    assert parameters[1].node.id not in project.evidence().contract_reads


def test_imported_class_name_shadowed_by_parameter_cannot_form_an_edge() -> None:
    base = _typescript("export class Base {}\n", "base.ts")
    child = _typescript(
        'import { Base } from "./base";\n'
        "class Replacement {}\n"
        "function factory(Base: typeof Replacement) { "
        "class Child extends Base {} return Child; }\n",
        "child.ts",
    )
    project = ProjectUsage((base, child))
    project.prepare()
    owner = child.class_scope("Child")
    assert owner is not None and owner.bases == []


def test_java_lexical_calls_resolve_private_static_members() -> None:
    source = Source(
        "View.java",
        b"class View {\n"
        b" private static int read() { return 1; }\n"
        b" static int execute() { return read(); }\n}\n",
        Language.JAVA,
    )
    index = SemanticIndex(JavaLanguage().parser.parse(source, Policy()), JavaSemanticSyntax())
    owner = index.class_scope("View")
    assert owner is not None
    assert owner.static_symbols["read"].reads


@pytest.mark.parametrize("receiver", ["Base", "Base()", "Child", "Child()"])
def test_python_static_methods_share_the_instance_attribute_namespace(receiver: str) -> None:
    source = Source(
        "view.py",
        (
            "class Base:\n    @staticmethod\n    def read() -> int:\n        return 1\n"
            "class Child(Base):\n    pass\n"
            f"print({receiver}.read())\n"
        ).encode(),
        Language.PYTHON,
    )
    index = SemanticIndex(PythonLanguage().parser.parse(source, Policy()), PythonSemanticSyntax())
    owner = index.class_scope("Base")
    assert owner is not None
    assert owner.symbols["read"].reads
    assert not index.unresolved_reads
