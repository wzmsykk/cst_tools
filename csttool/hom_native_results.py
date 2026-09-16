"""Strict native 0D result reader for the validated HOM project profile."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .hom_project_profile import HOM_PROFILE_V1, NativeScalarCapability


class NativeResultError(ValueError):
    """A required native CST result is missing or malformed."""


class NativeResultMissingError(NativeResultError, FileNotFoundError):
    """A required native result file does not exist."""


HomScalarSpec = NativeScalarCapability


@dataclass(frozen=True, slots=True)
class HomScalarValue:
    key: str
    value: float
    unit: str
    source_path: Path


HOM_NATIVE_SCALARS = HOM_PROFILE_V1.native_scalars

HOM_RESULT_CLASSIFICATION: Mapping[str, str] = MappingProxyType({
    **{spec.key: "native" for spec in HOM_NATIVE_SCALARS},
    **{key: "runtime-vba" for key in HOM_PROFILE_V1.runtime_vba_metrics},
})


def read_hom_native_results(expanded_project_dir: str | Path) -> Mapping[str, HomScalarValue]:
    result_dir = Path(expanded_project_dir) / "Result"
    values = {}
    for spec in HOM_NATIVE_SCALARS:
        path = result_dir / spec.relative_path
        values[spec.key] = HomScalarValue(
            key=spec.key,
            value=_read_strict_scalar(path),
            unit=spec.unit,
            source_path=path,
        )
    return MappingProxyType(values)


def _read_strict_scalar(path: Path) -> float:
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
