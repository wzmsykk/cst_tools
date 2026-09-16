"""Minimal, explicit project profile for the validated HOM workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from .runtime_protocol import Task


class ProfileValidationError(ValueError):
    """A task or CST project does not satisfy its declared profile."""


@dataclass(frozen=True, slots=True)
class ResultTemplateRequirement:
    result_name: str
    template_type: str
    template_name: str
    folder: str


@dataclass(frozen=True, slots=True)
class NativeScalarCapability:
    key: str
    relative_path: Path
    unit: str


@dataclass(frozen=True, slots=True)
class NativeRoverQCapability:
    axis: str
    xoffset_mm: float
    yoffset_mm: float
    zoffset_mm: float
    native_key: str


@dataclass(frozen=True, slots=True)
class HomProjectProfile:
    profile_id: str
    cst_year: int
    source_project: Path
    mutable_parameters: frozenset[str]
    required_templates: tuple[ResultTemplateRequirement, ...]
    native_scalars: tuple[NativeScalarCapability, ...]
    native_r_over_q: tuple[NativeRoverQCapability, ...]
    runtime_vba_metrics: frozenset[str]

    def validate_task(self, task: Task) -> None:
        names = {parameter.name for parameter in task.parameters}
        unsupported = names - self.mutable_parameters
        if unsupported:
            raise ProfileValidationError(
                f"profile {self.profile_id} does not allow parameters: "
                + ", ".join(sorted(unsupported))
            )

    def validate_inventory(self, records: Iterable[object]) -> None:
        actual = {
            (
                record.result_name,
                record.template_type,
                record.template_name,
                record.folder,
            )
            for record in records
        }
        missing = [
            requirement
            for requirement in self.required_templates
            if (
                requirement.result_name,
                requirement.template_type,
                requirement.template_name,
                requirement.folder,
            )
            not in actual
        ]
        if missing:
            names = ", ".join(item.result_name for item in missing)
            raise ProfileValidationError(
                f"profile {self.profile_id} is missing registered templates: {names}"
            )

    @property
    def native_scalar_by_key(self) -> Mapping[str, NativeScalarCapability]:
        return MappingProxyType({item.key: item for item in self.native_scalars})


_TEMPLATE_NAME = "3D Eigenmode Result"
_TEMPLATE_FOLDER = "2D and 3D Field Results"

HOM_PROFILE_V1 = HomProjectProfile(
    profile_id="hom-2022-v1",
    cst_year=2022,
    source_project=Path("project") / "HOM analysis" / "HOM analysis_clean.cst",
    mutable_parameters=frozenset({"fmin", "fmax"}),
    required_templates=tuple(
        ResultTemplateRequirement(name, "M0D", _TEMPLATE_NAME, _TEMPLATE_FOLDER)
        for name in (
            "Frequency (Multiple Modes)",
            "Q-Factor (Perturbation) (Multiple Modes)",
            "R over Q beta=1 (Multiple Modes)",
            "R over Q beta=1 (Multiple Modes)_offset1=5mm (Multiple Modes)",
            "R over Q beta=1 (Multiple Modes)_offset2=10mm (Multiple Modes)",
        )
    ),
    native_scalars=(
        NativeScalarCapability(
            "frequency", Path("Frequency (Multiple Modes)") / "Mode 1.rd0", "MHz"
        ),
        NativeScalarCapability(
            "q_factor",
            Path("Q-Factor (Perturbation) (Multiple Modes)") / "Mode 1.rd0",
            "1",
        ),
        NativeScalarCapability(
            "r_over_q",
            Path("R over Q beta=1 (Multiple Modes)") / "Mode 1.rd0",
            "ohm",
        ),
        NativeScalarCapability(
            "r_over_q_offset_5mm",
            Path("R over Q beta=1 (Multiple Modes)_offset1=5mm (Multiple Modes)")
            / "Mode 1.rd0",
            "ohm",
        ),
        NativeScalarCapability(
            "r_over_q_offset_10mm",
            Path("R over Q beta=1 (Multiple Modes)_offset2=10mm (Multiple Modes)")
            / "Mode 1.rd0",
            "ohm",
        ),
    ),
    native_r_over_q=(
        NativeRoverQCapability("z", 0, 0, 0, "r_over_q"),
        NativeRoverQCapability("z", 0, 5, 0, "r_over_q_offset_5mm"),
        NativeRoverQCapability("z", 0, 10, 0, "r_over_q_offset_10mm"),
    ),
    runtime_vba_metrics=frozenset(
        {"r_over_q_dynamic", "shunt_impedance", "total_loss", "voltage"}
    ),
)
