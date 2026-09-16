"""Minimal project-profile primitives shared by CST workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol

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


class ResultTemplateRecordLike(Protocol):
    result_name: str
    template_type: str
    template_name: str
    folder: str


@dataclass(frozen=True, slots=True)
class ProjectProfile:
    profile_id: str
    cst_year: int
    source_project: Path
    mutable_parameters: frozenset[str]
    required_templates: tuple[ResultTemplateRequirement, ...]
    native_scalars: tuple[NativeScalarCapability, ...]
    runtime_vba_metrics: frozenset[str]

    def validate_task(self, task: Task) -> None:
        names = {parameter.name for parameter in task.parameters}
        unsupported = names - self.mutable_parameters
        if unsupported:
            raise ProfileValidationError(
                f"profile {self.profile_id} does not allow parameters: "
                + ", ".join(sorted(unsupported))
            )

    def validate_inventory(self, records: Iterable[ResultTemplateRecordLike]) -> None:
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
