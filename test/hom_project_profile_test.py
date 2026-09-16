from dataclasses import replace

import pytest

from csttool.hom_project_profile import (
    HOM_PROFILE_V1,
    ProfileValidationError,
    ResultTemplateRequirement,
)
from csttool.hom_native_results import HOM_NATIVE_SCALARS
from csttool.hom_result_plan import HOM_NATIVE_R_OVER_Q, IntegrationLine
from csttool.protocol_hom_template_evaluation import ResultTemplateRecord
from csttool.runtime_protocol import Task, new_session_id


def _profile_inventory():
    return tuple(
        ResultTemplateRecord(
            item.result_name,
            item.template_type,
            item.template_name,
            item.folder,
        )
        for item in HOM_PROFILE_V1.required_templates
    )


def test_hom_profile_declares_only_validated_warm_mutations():
    assert HOM_PROFILE_V1.profile_id == "hom-2022-v1"
    assert HOM_PROFILE_V1.cst_year == 2022
    assert HOM_PROFILE_V1.mutable_parameters == frozenset({"fmin", "fmax"})

    task = Task.create(new_session_id(), {"fmin": "720", "fmax": "800"})
    HOM_PROFILE_V1.validate_task(task)

    unsupported = Task.create(new_session_id(), {"R": "229"})
    with pytest.raises(ProfileValidationError, match="does not allow parameters: R"):
        HOM_PROFILE_V1.validate_task(unsupported)


def test_hom_profile_requires_exact_registered_template_identity():
    inventory = _profile_inventory()
    HOM_PROFILE_V1.validate_inventory(inventory)

    with pytest.raises(ProfileValidationError, match="Frequency"):
        HOM_PROFILE_V1.validate_inventory(inventory[1:])

    wrong_type = replace(inventory[0], template_type="0D")
    with pytest.raises(ProfileValidationError, match="Frequency"):
        HOM_PROFILE_V1.validate_inventory((wrong_type, *inventory[1:]))


def test_native_readers_and_routing_are_derived_from_profile():
    assert HOM_NATIVE_SCALARS is HOM_PROFILE_V1.native_scalars
    assert HOM_NATIVE_R_OVER_Q == {
        IntegrationLine("z"): "r_over_q",
        IntegrationLine("z", yoffset_mm=5): "r_over_q_offset_5mm",
        IntegrationLine("z", yoffset_mm=10): "r_over_q_offset_10mm",
    }


def test_profile_can_represent_a_missing_required_template():
    missing = ResultTemplateRequirement(
        "P6 deliberately missing",
        "M0D",
        "3D Eigenmode Result",
        "2D and 3D Field Results",
    )
    profile = replace(
        HOM_PROFILE_V1,
        profile_id="hom-missing-test",
        required_templates=(*HOM_PROFILE_V1.required_templates, missing),
    )
    with pytest.raises(ProfileValidationError, match="P6 deliberately missing"):
        profile.validate_inventory(_profile_inventory())
