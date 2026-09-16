"""Minimal routing rules for HOM R/Q result evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .hom_project_profile import HomProjectProfile
from .result_provider import ResultProvider, select_result_provider


class ResultTemplatePhase(str, Enum):
    BEFORE_SOLVE = "before-solve"
    AFTER_SOLVE = "after-solve"


class UnsafeResultTemplateChange(ValueError):
    """A requested template change would invalidate solved field results."""


def _finite_offset(value: float | str, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a resolved numeric value") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return 0.0 if result == 0.0 else result


_AXIS_NUMBER = {"x": 1, "y": 2, "z": 3}
_TEMPLATE_COORDINATE = {"x": 0, "y": 1, "z": 2}


@dataclass(frozen=True, slots=True)
class IntegrationLine:
    axis: str
    xoffset_mm: float = 0.0
    yoffset_mm: float = 0.0
    zoffset_mm: float = 0.0

    def __post_init__(self) -> None:
        axis = self.axis.lower()
        if axis not in _AXIS_NUMBER:
            raise ValueError("axis must be x, y, or z")
        offsets = tuple(
            _finite_offset(value, name)
            for value, name in (
                (self.xoffset_mm, "xoffset_mm"),
                (self.yoffset_mm, "yoffset_mm"),
                (self.zoffset_mm, "zoffset_mm"),
            )
        )
        if offsets[_AXIS_NUMBER[axis] - 1] != 0.0:
            raise ValueError("offset along the integration axis must be zero")
        object.__setattr__(self, "axis", axis)
        object.__setattr__(self, "xoffset_mm", offsets[0])
        object.__setattr__(self, "yoffset_mm", offsets[1])
        object.__setattr__(self, "zoffset_mm", offsets[2])

    @property
    def axis_number(self) -> int:
        return _AXIS_NUMBER[self.axis]

    @property
    def template_coordinate(self) -> int:
        return _TEMPLATE_COORDINATE[self.axis]


HomRoverQRequest = IntegrationLine


@dataclass(frozen=True, slots=True)
class HomResultPlan:
    provider: ResultProvider
    native_key: str | None
    integration_line: IntegrationLine


def native_r_over_q_for_profile(
    profile: HomProjectProfile,
) -> Mapping[IntegrationLine, str]:
    return MappingProxyType(
        {
            IntegrationLine(
                item.axis,
                item.xoffset_mm,
                item.yoffset_mm,
                item.zoffset_mm,
            ): item.native_key
            for item in profile.native_r_over_q
        }
    )


def _default_hom_profile() -> HomProjectProfile:
    from .hom_project_profile import HOM_PROFILE_V1

    return HOM_PROFILE_V1


HOM_NATIVE_R_OVER_Q = native_r_over_q_for_profile(_default_hom_profile())


def plan_hom_r_over_q(
    request: IntegrationLine,
    native_results: Mapping[IntegrationLine, str] | None = None,
    *,
    profile: HomProjectProfile | None = None,
) -> HomResultPlan:
    if native_results is not None and profile is not None:
        raise ValueError("pass either native_results or profile, not both")
    if native_results is None:
        native_results = native_r_over_q_for_profile(
            profile if profile is not None else _default_hom_profile()
        )
    selection = select_result_provider(request, native_results)
    return HomResultPlan(selection.provider, selection.native_key, request)


def integration_line_from_template_settings(
    settings: Mapping[str, str],
) -> IntegrationLine:
    if str(settings.get("maxrange", "1")) != "1":
        raise ValueError("only full-range Result Template integration is supported")
    try:
        coordinate = int(settings["coordinates"])
        axis = ("x", "y", "z")[coordinate]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("Result Template coordinates must be 0, 1, or 2") from exc
    offsets = [
        _finite_offset(settings.get(key, "0"), key) for key in ("u1", "v1", "w1")
    ]
    offsets[coordinate] = 0.0
    return IntegrationLine(axis, *offsets)


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
