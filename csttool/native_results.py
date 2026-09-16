"""Strict readers for native scalar results declared by a project profile."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from .project_profile import NativeScalarCapability, ProjectProfile


class NativeResultError(ValueError):
    """A required native CST result is missing or malformed."""


class NativeResultMissingError(NativeResultError, FileNotFoundError):
    """A required native result file does not exist."""


@dataclass(frozen=True, slots=True)
class NativeScalarValue:
    key: str
    value: float
    unit: str
    source_path: Path


def result_classification(profile: ProjectProfile) -> Mapping[str, str]:
    return MappingProxyType({
        **{spec.key: "native" for spec in profile.native_scalars},
        **{key: "runtime-vba" for key in profile.runtime_vba_metrics},
    })


def read_native_scalar_results(
    expanded_project_dir: str | Path,
    capabilities: Iterable[NativeScalarCapability],
) -> Mapping[str, NativeScalarValue]:
    result_dir = Path(expanded_project_dir) / "Result"
    values = {}
    for spec in capabilities:
        path = result_dir / spec.relative_path
        values[spec.key] = NativeScalarValue(
            key=spec.key,
            value=read_strict_scalar(path),
            unit=spec.unit,
            source_path=path,
        )
    return MappingProxyType(values)


def read_profile_native_results(
    expanded_project_dir: str | Path,
    profile: ProjectProfile,
) -> Mapping[str, NativeScalarValue]:
    return read_native_scalar_results(expanded_project_dir, profile.native_scalars)


def read_strict_scalar(path: str | Path) -> float:
    path = Path(path)
    if not path.is_file():
        raise NativeResultMissingError(f"native CST result is missing: {path}")
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) != 1 or not lines[0].strip():
        raise NativeResultError(f"native CST result must contain one scalar line: {path}")
    try:
        value = float(lines[0].strip())
    except ValueError as exc:
        raise NativeResultError(f"native CST result is not numeric: {path}") from exc
    if not math.isfinite(value):
        raise NativeResultError(f"native CST result is not finite: {path}")
    return value
