"""Call-specific generic results preserve void, value and unresolved evidence."""

import pytest

from code_harness.diagnostics import Finding
from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source

_TRANSACT = "function transact<R>(work: () => R): R { return work(); }\n"


def _returns(code: str, language: Language = Language.TYPESCRIPT) -> tuple[Finding, ...]:
    return tuple(
        finding
        for finding in check(Source("generic-result", code.encode(), language), Policy())
        if finding.rule == "unused.return"
    )


def test_handoff_coordinates_and_consumed_result() -> None:
    code = (
        "export function transact<Result>(work: () => Result): Result {\n"
        "    return work();\n}\nlet calls = 0;\n"
        "transact(() => { calls += 1; });\ntransact(() => 42);\n"
        "const value = transact(() => 42);\nconsole.log(value, calls);\n"
        "transact(async () => { calls += 1; });\n"
    )
    findings = _returns(code)
    assert [(f.path, f.line, f.column, f.rule, f.severity) for f in findings] == [
        ("generic-result", 6, 1, "unused.return", "warning"),
        ("generic-result", 9, 1, "unused.return", "warning"),
    ]


@pytest.mark.parametrize("language", [Language.TYPESCRIPT, Language.TSX])
@pytest.mark.parametrize(
    "callback",
    ["() => {}", "() => { return; }", "() => effect()", "function () { effect(); }", "named"],
)
def test_void_callbacks(language: Language, callback: str) -> None:
    code = _TRANSACT + "function effect(): void {}\nfunction named(): void {}\n"
    assert _returns(code + f"transact({callback});", language) == ()


@pytest.mark.parametrize(
    "callback",
    [
        "() => 42",
        "() => 'value'",
        "() => ({ value: 1 })",
        "async () => {}",
        "function* () {}",
        "() => { if (condition) return 1; }",
        "() => external()",
        "unknownCallback",
        "() => { throw new Error(); return 1; }",
    ],
)
def test_value_and_unresolved_callbacks_remain_reported(callback: str) -> None:
    assert len(_returns(_TRANSACT + f"transact({callback});")) == 1


@pytest.mark.parametrize(
    "call",
    [
        "transact<void>(() => 42);",
        "const callback: () => void = () => 42; transact(callback);",
        "function callback(): void { return; } transact(callback);",
        "function use(callback: () => void): void { transact(callback); }",
    ],
)
def test_selected_declared_contract_controls_result(call: str) -> None:
    assert _returns(_TRANSACT + call) == ()


@pytest.mark.parametrize(
    "declaration",
    [
        "function transact<R>(work: () => R): Promise<R> { return Promise.resolve(work()); }",
        "function transact<R>(work: () => R): { value: R } { return { value: work() }; }",
        "async function transact<R>(work: () => R): Promise<R> { return work(); }",
    ],
)
def test_wrapped_results_are_values(declaration: str) -> None:
    assert len(_returns(declaration + "\ntransact(() => {});")) == 1


def test_nested_forwarding_and_recursive_callback() -> None:
    code = _TRANSACT + (
        "function effect(): void {}\n"
        "function recursive() { return recursive(); }\n"
        "transact(() => transact(() => effect()));\n"
        "transact(() => transact(() => 42));\n"
        "transact(recursive);\n"
    )
    assert [f.line for f in _returns(code)] == [5, 6]


def test_instance_method_classifies_each_call_independently() -> None:
    code = (
        "class State {\n"
        " transaction<R>(work: () => R): R { return work(); }\n"
        " run(): void {\n"
        "  this.transaction(() => {});\n"
        "  this.transaction(() => 42);\n"
        " }\n}\n"
        "const state = new State();\nstate.transaction(() => {});\n"
        "state.transaction(() => 'value');\n"
    )
    assert [(f.line, f.column) for f in _returns(code)] == [(5, 3), (10, 1)]


@pytest.mark.parametrize(
    "code",
    [
        _TRANSACT + "let cb = () => {}; cb = () => 1; transact(cb);",
        _TRANSACT + "function cb(): void {} cb = () => 1; transact(cb);",
        "function transact<R>(work: () => R, seed: R): R { return work(); }\n"
        "transact(() => {}, 1);",
        "function transact<R>(work: () => R, seed: R[]): R { return work(); }\n"
        "transact(() => {}, [1]);",
        "function transact<R>(work: () => R): R;\n"
        "function transact(work: () => number): number;\n"
        "function transact<R>(work: () => R): R { return work(); }\n"
        "transact(() => {});",
        _TRANSACT + "function callback(): number;\n"
        "function callback(value: number): void;\n"
        "function callback(value?: number) {}\ntransact(callback);",
        "function transact<R>(work: (value: R) => R, seed: R): R { return work(seed); }\n"
        "transact(value => value, 42);",
        "function transact<R>(work: <R>() => R): R { return external(); }\ntransact(() => {});",
        "function transact<R>({a,b}: Pair, work: () => R, ...extra: (() => void)[]): R "
        "{ return work(); }\ntransact({a:1,b:2}, () => 42, () => {});",
    ],
)
def test_ambiguous_evidence_retains_fallback(code: str) -> None:
    assert len(_returns(code)) == 1


@pytest.mark.parametrize("generic", ["[R]", ""])
def test_python_generic_none_and_value_results(generic: str) -> None:
    code = (
        "from typing import Callable, TypeVar\nR = TypeVar('R')\n"
        f"def transact{generic}(work: Callable[[], R]) -> R:\n    return work()\n"
        "def nothing() -> None:\n    pass\n"
        "async def asynchronous() -> None:\n    pass\n"
        "transact(nothing)\ntransact(lambda: None)\ntransact(lambda: nothing())\n"
        "transact(lambda: 42)\ntransact(asynchronous)\n"
        "value = transact(lambda: 42)\n"
    )
    assert [f.line for f in _returns(code, Language.PYTHON)] == [12, 13]


@pytest.mark.parametrize(
    "callback",
    ["lambda: 'value'", "lambda: {'value': 1}", "lambda: external()", "unknown_callback"],
)
def test_python_value_and_unresolved_callbacks(callback: str) -> None:
    code = (
        "from collections.abc import Callable\n"
        "def transact[R](work: Callable[[], R]) -> R:\n    return work()\n"
        f"transact({callback})\n"
    )
    assert len(_returns(code, Language.PYTHON)) == 1


@pytest.mark.parametrize(
    ("setup", "call", "warnings"),
    [
        ("def callback() -> None:\n    return None\n", "transact(callback)", 0),
        ("def callback():\n    yield 1\n", "transact(callback)", 1),
        ("def callback():\n    if flag:\n        return 1\n", "transact(callback)", 1),
        ("def callback() -> None:\n    pass\n", "transact(work=callback)", 1),
        ("", "transact()", 1),
        ("", "transact(lambda: (None))", 0),
        ("", "transact(lambda: (1, 2))", 1),
        ("callback: Callable[[], None] = lambda: None\n", "transact(callback)", 0),
        ("def use(work: Callable[[], None]) -> None:\n    transact(work)\n", "use(external)", 0),
    ],
)
def test_python_callback_contract_controls(setup: str, call: str, warnings: int) -> None:
    code = (
        "from typing import Callable\n"
        "def transact[R](work: Callable[[], R]) -> R:\n    return work()\n" + setup + call + "\n"
    )
    assert len(_returns(code, Language.PYTHON)) == warnings


@pytest.mark.parametrize("result", ["list[R]", "tuple[R]"])
def test_python_wrapped_generic_results(result: str) -> None:
    code = (
        "from typing import Callable\n"
        f"def transact[R](work: Callable[[], R]) -> {result}:\n    return [work()]\n"
        "transact(lambda: None)\n"
    )
    assert len(_returns(code, Language.PYTHON)) == 1


def test_javascript_callback_forwarding() -> None:
    code = (
        "function transact(work) { return work(); }\n"
        "transact(() => {});\ntransact(() => 42);\ntransact(async () => {});\n"
        "function changed(work) { work = external; return work(); }\n"
        "changed(() => {});\n"
    )
    assert [f.line for f in _returns(code, Language.JAVASCRIPT)] == [3, 4, 6]


def test_java_boxed_void_is_a_value() -> None:
    code = (
        "class Sample {\n"
        " static <R> R transact(java.util.function.Supplier<R> work) { return work.get(); }\n"
        " static void effect() {}\n"
        " static void run() { effect(); Sample.<Void>transact(() -> null); }\n}\n"
    )
    assert len(_returns(code, Language.JAVA)) == 1


def test_go_empty_struct_is_a_value() -> None:
    code = (
        "package sample\n"
        "func transact[R any](work func() R) R { return work() }\n"
        "func effect() {}\n"
        "func Run() { effect(); transact(func() struct{} { return struct{}{} }) }\n"
    )
    assert len(_returns(code, Language.GO)) == 1
