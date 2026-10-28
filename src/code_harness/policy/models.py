"""Explicit typed composition of checker-owned policy fragments."""

from pydantic import Field

from code_harness.architecture.options import ArchitectureCheckers
from code_harness.architecture.options import Boundary as Boundary
from code_harness.architecture.options import ImportOptions as ImportOptions
from code_harness.architecture.options import ObjectModelOptions as ObjectModelOptions
from code_harness.architecture.options import Owner as Owner
from code_harness.architecture.options import OwnershipOptions as OwnershipOptions
from code_harness.architecture.options import SourcePlacement as SourcePlacement
from code_harness.architecture.options import StructureOptions as StructureOptions
from code_harness.metrics.options import FunctionSizeOptions as FunctionSizeOptions
from code_harness.metrics.options import MetricCheckers
from code_harness.policy.contracts import CheckerOptions as CheckerOptions
from code_harness.policy.contracts import Contract as Contract
from code_harness.policy.type_options import TypeCheckers
from code_harness.semantics.encoding_options import BroadTypeOptions as BroadTypeOptions
from code_harness.semantics.encoding_options import EncodingCheckers
from code_harness.semantics.encoding_options import EncodingOptions as EncodingOptions
from code_harness.semantics.encoding_options import OutputApi as OutputApi
from code_harness.semantics.options import SemanticCheckers
from code_harness.semantics.projection.options import ProjectionCheckers


class Checkers(
    MetricCheckers,
    ArchitectureCheckers,
    EncodingCheckers,
    SemanticCheckers,
    TypeCheckers,
    ProjectionCheckers,
):
    """Compose supported checker schemas without redeclaring their options or identities."""


class Policy(Contract):
    """Select source files globally and configure each checker independently."""

    version: int = Field(default=2, ge=2, le=2)
    include: tuple[str, ...] = ("**",)
    exclude: tuple[str, ...] = ()
    third_party_modules: tuple[str, ...] = ()
    checkers: Checkers = Checkers()
