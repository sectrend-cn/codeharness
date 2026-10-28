"""Inherited method contracts share corresponding parameter-read evidence."""

from pathlib import Path

import pytest

from code_harness.engine import check, registry
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


def _unread(code: str, language: Language = Language.PYTHON) -> tuple[str, ...]:
    findings = check(Source("sample", code.encode(), language), Policy())
    return tuple(finding.message for finding in findings if finding.rule == "unused.parameter")


@pytest.mark.parametrize("bodies", [("0", "value"), ("value", "0")])
def test_override_read_preserves_the_shared_parameter(bodies: tuple[str, str]) -> None:
    base, child = bodies
    code = (
        f"class Base:\n    def run(self, value: int) -> int:\n        return {base}\n"
        f"class Child(Base):\n    def run(self, value: int) -> int:\n        return {child}\n"
    )
    assert _unread(code) == ()


def test_metric_implementations_share_node_and_source_parameters() -> None:
    root = Path(__file__).parents[1]
    paths = (
        "src/code_harness/languages/metric_syntax.py",
        "src/code_harness/languages/python/syntax.py",
        "src/code_harness/languages/go/syntax.py",
    )
    sources = tuple(Source(path, (root / path).read_bytes(), Language.PYTHON) for path in paths)
    findings = registry().analyze_sources((sources[0],), Policy(), sources)
    assert not any(finding.rule == "unused.parameter" for finding in findings)


def test_each_unread_override_slot_is_still_reported() -> None:
    code = (
        "class Base:\n    def run(self, value: int) -> int:\n        return 0\n"
        "class Child(Base):\n    def run(self, value: int) -> int:\n        return 1\n"
    )
    assert len(_unread(code)) == 2
    assert all("'value'" in message for message in _unread(code))


def test_unrelated_method_does_not_exempt_an_unread_parameter() -> None:
    code = (
        "class Base:\n    def run(self, value: int) -> int:\n        return 0\n"
        "class Other:\n    def run(self, value: int) -> int:\n        return value\n"
    )
    assert len(_unread(code)) == 1


def test_extra_override_parameter_remains_unused() -> None:
    code = (
        "class Base:\n    def run(self, value: int) -> int:\n        return 0\n"
        "class Child(Base):\n"
        "    def run(self, renamed: int, extra: int = 0) -> int:\n        return renamed\n"
    )
    unread = _unread(code)
    assert len(unread) == 1
    assert "'extra'" in unread[0]


def test_transitive_and_sibling_overrides_share_parameter_usage() -> None:
    code = (
        "class Base:\n    def run(self, first: int, second: int) -> int:\n        return 0\n"
        "class Middle(Base):\n    pass\n"
        "class Left(Middle):\n"
        "    def run(self, first: int, second: int) -> int:\n        return first\n"
        "class Right(Base):\n"
        "    def run(self, first: int, second: int) -> int:\n        return second\n"
    )
    assert _unread(code) == ()


def test_keyword_only_parameters_match_names_despite_reordering() -> None:
    code = (
        "class Base:\n"
        "    def run(self, *, left: int, right: int) -> int:\n        return 0\n"
        "class Child(Base):\n"
        "    def run(self, *, right: int, left: int) -> int:\n        return left\n"
    )
    unread = _unread(code)
    assert len(unread) == 2
    assert all("'right'" in message for message in unread)


def test_variadic_override_keeps_its_positional_and_keyword_slots_separate() -> None:
    code = (
        "class Base:\n"
        "    def run(self, *values: int, flag: int = 0, **options: int) -> int:\n"
        "        return 0\nclass Child(Base):\n"
        "    def run(self, *items: int, flag: int = 0, **settings: int) -> int:\n"
        "        return len(items) + flag + len(settings)\n"
    )
    assert _unread(code) == ()


def test_constructor_signatures_do_not_form_override_contracts() -> None:
    code = (
        "class Base:\n    def __init__(self, value: int) -> None:\n        pass\n"
        "class Child(Base):\n"
        "    def __init__(self, value: int) -> None:\n        print(value)\n"
    )
    assert len(_unread(code)) == 1


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT, Language.TSX])
def test_extends_contract_uses_positional_arguments(language: Language) -> None:
    code = (
        "class Base { run(value) { return 0; } } "
        "class Child extends Base { run(renamed) { return renamed; } }"
    )
    assert _unread(code, language) == ()


def test_cross_file_override_read_applies_to_the_selected_base_snapshot() -> None:
    base = Source(
        "base.py",
        b"class Base:\n    def run(self, value: int) -> int:\n        return 0\n",
        Language.PYTHON,
    )
    child = Source(
        "child.py",
        b"from base import Base as Parent\nclass Child(Parent):\n"
        b"    def run(self, renamed: int) -> int:\n        return renamed\n",
        Language.PYTHON,
    )
    assert any(f.rule == "unused.parameter" for f in check(base, Policy()))
    findings = registry().analyze_sources((base,), Policy(), (base, child))
    assert not any(f.rule == "unused.parameter" for f in findings)


@pytest.mark.parametrize("linked", [True, False])
def test_protocol_usage_requires_an_explicit_implementation_link(linked: bool) -> None:
    base = "(Operation[str])" if linked else ""
    code = (
        "from typing import Protocol\n"
        "class Operation[T](Protocol):\n"
        "    def run(self, value: int, unused: int) -> T: ...\n"
        "class Reader(Operation[int]):\n"
        "    def run(self, value: int, unused: int) -> int:\n        return value\n"
        f"class Constant{base}:\n"
        "    def run(self, value: int, unused: int) -> str:\n        return 'constant'\n"
    )
    unread = _unread(code)
    assert sum("'value'" in message for message in unread) == (0 if linked else 1)
    assert sum("'unused'" in message for message in unread) == 2


def test_imported_generic_protocol_links_selected_implementation_to_reader() -> None:
    contract = Source(
        "contract.py",
        b"from typing import Protocol\nclass Operation[T](Protocol):\n"
        b"    def run(self, value: int) -> T: ...\n",
        Language.PYTHON,
    )
    reader = Source(
        "reader.py",
        b"from contract import Operation\nclass Reader(Operation[int]):\n"
        b"    def run(self, value: int) -> int:\n        return value\n",
        Language.PYTHON,
    )
    constant = Source(
        "constant.py",
        b"from contract import Operation as Contract\nclass Constant(Contract[str]):\n"
        b"    def run(self, value: int) -> str:\n        return 'constant'\n",
        Language.PYTHON,
    )
    analyzers = registry()
    isolated = analyzers.analyze_sources((constant,), Policy(), (contract, constant))
    assert any(f.rule == "unused.parameter" for f in isolated)
    linked = analyzers.analyze_sources((constant,), Policy(), (contract, constant, reader))
    assert not any(f.rule == "unused.parameter" for f in linked)


@pytest.mark.parametrize(
    ("operation", "unused"), [("return self.value", 1), ("self.value = 3\n        return 0", 3)]
)
def test_inherited_field_reads_do_not_exempt_writes_or_unrelated_owners(
    operation: str, unused: int
) -> None:
    code = (
        "class Base:\n    value: int = 0\n"
        f"    def run(self) -> int:\n        {operation}\n"
        "class Child(Base):\n    value: int = 1\n"
        "class Other:\n    value: int = 2\n"
    )
    findings = check(Source("sample.py", code.encode(), Language.PYTHON), Policy())
    fields = [finding for finding in findings if finding.rule == "unused.field"]
    assert len(fields) == unused
    assert all("'value'" in finding.message for finding in fields)


@pytest.mark.parametrize(("caller", "unused"), [("run", 1), ("convert", 3)])
def test_method_overrides_require_a_nonrecursive_read_in_their_resolved_family(
    caller: str, unused: int
) -> None:
    implementation = "    def convert(self) -> int:\n        return 0\n" if caller == "run" else ""
    code = (
        "class Base:\n"
        f"    def {caller}(self) -> int:\n        return self.convert()\n"
        f"{implementation}"
        "class Child(Base):\n    def convert(self) -> int:\n        return 1\n"
        "class Other:\n    def convert(self) -> int:\n        return 2\n"
    )
    findings = check(Source("sample.py", code.encode(), Language.PYTHON), Policy())
    methods = [
        finding
        for finding in findings
        if finding.rule == "unused.function" and "'convert'" in finding.message
    ]
    assert len(methods) == unused


def test_cross_file_base_read_preserves_overridden_field() -> None:
    base = Source(
        "base.py",
        b"class Base:\n    value: int = 0\n    def read(self) -> int:\n        return self.value\n",
        Language.PYTHON,
    )
    child = Source(
        "child.py",
        b"from base import Base\nclass Child(Base):\n    value: int = 1\n",
        Language.PYTHON,
    )
    isolated = check(child, Policy())
    assert any(finding.rule == "unused.field" for finding in isolated)
    findings = registry().analyze_sources((child,), Policy(), (base, child))
    assert not any(finding.rule == "unused.field" for finding in findings)


def test_explicit_base_class_read_does_not_exempt_child_field_override() -> None:
    code = (
        "class Base:\n    value: int = 0\n"
        "class Child(Base):\n    value: int = 1\n"
        "print(Base.value)\n"
    )
    findings = check(Source("sample.py", code.encode(), Language.PYTHON), Policy())
    fields = [finding for finding in findings if finding.rule == "unused.field"]
    assert len(fields) == 1
    assert fields[0].line == 4


def test_explicit_base_method_reference_does_not_exempt_child_override() -> None:
    code = (
        "class Base:\n    def convert(self) -> int:\n        return 0\n"
        "class Child(Base):\n    def convert(self) -> int:\n        return 1\n"
        "print(Base.convert)\n"
    )
    findings = check(Source("sample.py", code.encode(), Language.PYTHON), Policy())
    methods = [finding for finding in findings if finding.rule == "unused.function"]
    assert len(methods) == 1
    assert methods[0].line == 5


def test_concrete_base_instance_read_does_not_exempt_child_field_override() -> None:
    code = (
        "class Base:\n    value: int = 0\n"
        "class Child(Base):\n    value: int = 1\n"
        "base = Base()\nprint(base.value)\n"
    )
    findings = check(Source("sample.py", code.encode(), Language.PYTHON), Policy())
    fields = [finding for finding in findings if finding.rule == "unused.field"]
    assert len(fields) == 1
    assert fields[0].line == 4
