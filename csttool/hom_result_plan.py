"""Minimal routing rules for HOM R/Q result evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class ResultProvider(str, Enum):
    NATIVE = "native"
    RUNTIME_VBA = "runtime-vba"


class ResultTemplatePhase(str, Enum):
    BEFORE_SOLVE = "before-solve"
    AFTER_SOLVE = "after-solve"


class UnsafeResultTemplateChange(ValueError):
    """A requested template change would invalidate solved field results."""


@dataclass(frozen=True, slots=True)
class HomRoverQRequest:
    axis: str
    xoffset_mm: float
    yoffset_mm: float


@dataclass(frozen=True, slots=True)
class HomResultPlan:
    provider: ResultProvider
    native_key: str | None


_NATIVE_R_OVER_Q = {
    ("z", 0.0, 0.0): "r_over_q",
    ("z", 0.0, 5.0): "r_over_q_offset_5mm",
    ("z", 0.0, 10.0): "r_over_q_offset_10mm",
}


def plan_hom_r_over_q(request: HomRoverQRequest) -> HomResultPlan:
    axis = request.axis.lower()
    xoffset = _finite_offset(request.xoffset_mm, "xoffset_mm")
    yoffset = _finite_offset(request.yoffset_mm, "yoffset_mm")
    native_key = _NATIVE_R_OVER_Q.get((axis, xoffset, yoffset))
    if native_key is not None:
        return HomResultPlan(ResultProvider.NATIVE, native_key)
    return HomResultPlan(ResultProvider.RUNTIME_VBA, None)


def validate_result_template_change(
    phase: ResultTemplatePhase,
    *,
    changes_project_parameters: bool,
) -> None:
    if phase is ResultTemplatePhase.AFTER_SOLVE and changes_project_parameters:
        raise UnsafeResultTemplateChange(
            "post-solve Result Template evaluation must not change project parameters; "
            "Update Params invalidates solved results"
        )


def _finite_offset(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return 0.0 if result == 0.0 else result
