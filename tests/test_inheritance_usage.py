"""Inheritance reads retain declaration, receiver and immutable snapshot identity."""

import pytest

from code_harness.diagnostics import Finding
from code_harness.engine import check, registry
from code_harness.policy.models import Policy
from code_harness.source import Language, Source

_TRACE = """abstract class TraceNodeView {
    render(): string {
        return `${this.className()}|${this.traceId()}|${this.timestamp()}|${this.title()}`;
    }
    protected abstract traceId(): string;
    protected abstract className(): string;
    protected abstract timestamp(): string;
    protected abstract title(): string;
}
abstract class ActivityTraceView<K extends string> extends TraceNodeView {
    constructor(protected readonly kind: K) { super(); }
    override render(): string { return `${super.render()}|${this.kind}`; }
    protected traceId(): string { return "entry-1"; }
    protected className(): string { return `trace-${this.kind}`; }
    protected timestamp(): string { return "2026-10-15"; }
}
class InputTraceView extends ActivityTraceView<"input"> {
    protected title(): string { return "Message"; }
}
function _viewFor(): TraceNodeView { return new InputTraceView("input"); }
export function renderActivity(): string { return _viewFor().render(); }
"""


def _unused(code: str, language: Language) -> tuple[Finding, ...]:
    return tuple(
        f
        for f in check(Source("sample", code.encode(), language), Policy())
        if f.rule == "unused.function"
    )


@pytest.mark.parametrize("language", [Language.TYPESCRIPT, Language.TSX])
@pytest.mark.parametrize("concrete", [False, True])
def test_abstract_generic_template_method_handoff(language: Language, concrete: bool) -> None:
    code = _TRACE
    if concrete:
        code = code.replace(
            'function _viewFor(): TraceNodeView { return new InputTraceView("input"); }',
            'const view = new InputTraceView("input");',
        ).replace("_viewFor().render()", "view.render()")
    assert check(Source("trace.ts", code.encode(), language), Policy()) == ()


@pytest.mark.parametrize("language", [Language.TYPESCRIPT, Language.TSX])
def test_abstract_owner_does_not_exempt_dead_or_unrelated_methods(language: Language) -> None:
    code = _TRACE + (
        "abstract class Unused extends TraceNodeView {\n"
        "    idle(): string { return 'unused'; }\n"
        "}\n"
        "class Other {\n"
        "    render(): string { return 'other'; }\n"
        "    title(): string { return 'other'; }\n"
        "}\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [(23, 5), (26, 5), (27, 5)]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_concrete_leaf_does_not_read_replaced_ancestors_or_siblings(language: Language) -> None:
    code = (
        "class Base { run() { return 0; } }\n"
        "class Middle extends Base { run() { return 1; } }\n"
        "class Leaf extends Middle { run() { return 2; } }\n"
        "class Sibling extends Base { run() { return 3; } }\n"
        "const leaf = new Leaf(); console.log(leaf.run());\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [(1, 14), (2, 29), (4, 30)]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_super_reads_base_body_without_exempting_unrelated_names(language: Language) -> None:
    code = (
        "class Base { run() { return this.hook(); } hook() { return 0; } }\n"
        "class Child extends Base { run() { return super.run(); } hook() { return 1; } }\n"
        "class Other { run() { return 2; } }\n"
        "const child = new Child(); console.log(child.run());\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [(3, 15)]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_instance_read_does_not_use_static_override(language: Language) -> None:
    code = (
        "class Base { run() { return this.hook(); } hook() { return 0; } }\n"
        "class Child extends Base { static hook() { return 1; } }\n"
        "const base = new Base(); console.log(base.run());\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [(2, 35)]


def test_typed_child_receiver_does_not_reach_ancestor_or_sibling_override() -> None:
    code = (
        "class Base { run(): number { return 0; } }\n"
        "class Child extends Base { run(): number { return 1; } }\n"
        "class Sibling extends Base { run(): number { return 2; } }\n"
        "export function execute(child: Child): number { return child.run(); }\n"
    )
    assert [(f.line, f.column) for f in _unused(code, Language.TYPESCRIPT)] == [(1, 14), (3, 30)]


def test_python_template_method_and_super_preserve_unrelated_findings() -> None:
    code = (
        "from abc import ABC, abstractmethod\n"
        "class Base(ABC):\n"
        "    def render(self) -> str:\n        return self.hook()\n"
        "    @abstractmethod\n    def hook(self) -> str: ...\n"
        "class Middle(Base):\n"
        "    def render(self) -> str:\n        return super().render()\n"
        "    def hook(self) -> str:\n        return 'used'\n"
        "class Leaf(Middle):\n    pass\n"
        "class Other:\n    def render(self) -> str:\n        return 'unused'\n"
        "def factory() -> Base:\n    return Leaf()\n"
        "print(factory().render())\n"
    )
    assert [(f.line, f.column) for f in _unused(code, Language.PYTHON)] == [(15, 9)]


@pytest.mark.parametrize("language", [Language.TYPESCRIPT, Language.TSX])
def test_imported_abstract_chain_retains_exact_declarations(language: Language) -> None:
    base, remainder = _TRACE.split("abstract class ActivityTraceView", 1)
    middle, leaf = ("abstract class ActivityTraceView" + remainder).split("class InputTraceView", 1)
    sources = (
        Source("base.ts", ("export " + base).encode(), language),
        Source(
            "middle.ts",
            ('import { TraceNodeView } from "./base";\nexport ' + middle).encode(),
            language,
        ),
        Source(
            "leaf.ts",
            (
                'import { TraceNodeView } from "./base";\n'
                'import { ActivityTraceView } from "./middle";\nclass InputTraceView' + leaf
            ).encode(),
            language,
        ),
    )
    assert registry().analyze_sources(sources, Policy()) == ()


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
@pytest.mark.parametrize("receiver, unused", [("Item", (2, 5)), ("new Item()", (3, 12))])
def test_static_and_instance_methods_in_one_class_have_distinct_declarations(
    language: Language, receiver: str, unused: tuple[int, int]
) -> None:
    code = (
        "class Item {\n"
        "    read() { return 1; }\n"
        "    static read() { return 2; }\n"
        "}\n"
        f"console.log(({receiver}).read());\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [unused]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_unread_override_contract_still_reports_every_body(language: Language) -> None:
    code = (
        "class Base { run() { return 0; } }\n"
        "class Middle extends Base { run() { return 1; } }\n"
        "class Leaf extends Middle {}\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [(1, 14), (2, 29)]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_shadowed_base_does_not_share_parameter_usage(language: Language) -> None:
    code = (
        "class Base { run(value) { return value; } }\n"
        "function factory(Base) {\n"
        "    class Child extends Base { run(value) { return 1; } }\n"
        "    return Child;\n"
        "}\nconsole.log(factory(Base));\n"
    )
    findings = check(Source("sample", code.encode(), language), Policy())
    assert [(f.line, f.column) for f in findings if f.rule == "unused.parameter"] == [(3, 36)]


def test_generic_argument_is_not_a_second_base_class() -> None:
    code = (
        "class Argument { run(value: number): number { return value; } }\n"
        "class Base<T> { }\n"
        "class Child extends Base<Argument> { run(value: number): number { return 1; } }\n"
    )
    findings = check(Source("sample.ts", code.encode(), Language.TYPESCRIPT), Policy())
    assert [(f.line, f.column) for f in findings if f.rule == "unused.parameter"] == [(3, 42)]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_local_shadowing_removes_provisional_inheritance_edges(language: Language) -> None:
    code = (
        "class Base { run(value) { return value; } }\n"
        "class Other {}\n"
        "function factory() {\n"
        "    const Base = Other;\n"
        "    class Child extends Base { run(value) { return 1; } }\n"
        "    return Child;\n}\nconsole.log(factory());\n"
    )
    findings = check(Source("sample", code.encode(), language), Policy())
    assert [(f.line, f.column) for f in findings if f.rule == "unused.parameter"] == [(5, 36)]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_static_super_reads_only_the_static_base_declaration(language: Language) -> None:
    code = (
        "class Base {\n"
        "    read() { return 1; }\n"
        "    static read() { return 2; }\n}\n"
        "class Child extends Base {\n"
        "    static read() { return super.read(); }\n}\n"
        "console.log(Child.read());\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [(2, 5)]


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_inherited_static_method_is_not_hidden_by_an_instance_method(language: Language) -> None:
    code = (
        "class Base { static read() { return 1; } }\n"
        "class Child extends Base { read() { return 2; } }\n"
        "console.log(Child.read());\n"
    )
    assert [(f.line, f.column) for f in _unused(code, language)] == [(2, 28)]
