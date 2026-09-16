"""Strict native 0D result reader for the validated HOM project profile."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .hom_project_profile import (
    HOM_PROFILE_V1,
    HomProjectProfile,
    NativeScalarCapability,
)
from .native_results import (
    NativeResultError,
    NativeResultMissingError,
    NativeScalarValue,
    read_profile_native_results,
    result_classification,
)


HomScalarSpec = NativeScalarCapability


HomScalarValue = NativeScalarValue


HOM_NATIVE_SCALARS = HOM_PROFILE_V1.native_scalars

def hom_result_classification(
    profile: HomProjectProfile = HOM_PROFILE_V1,
) -> Mapping[str, str]:
    return result_classification(profile)


HOM_RESULT_CLASSIFICATION = hom_result_classification()


def read_hom_native_results(
    expanded_project_dir: str | Path,
    profile: HomProjectProfile = HOM_PROFILE_V1,
) -> Mapping[str, HomScalarValue]:
    return read_profile_native_results(expanded_project_dir, profile)
