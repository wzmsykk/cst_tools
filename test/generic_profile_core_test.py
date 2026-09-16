from pathlib import Path

import pytest

from csttool.native_results import (
    NativeResultError,
    read_native_scalar_results,
    result_classification,
)
from csttool.project_profile import (
    NativeScalarCapability,
    ProfileValidationError,
    ProjectProfile,
    ResultTemplateRequirement,
)
from csttool.result_provider import ResultProvider, select_result_provider
from csttool.runtime_protocol import Task, new_session_id


def _profile() -> ProjectProfile:
    return ProjectProfile(
        profile_id="generic-test-v1",
        cst_year=2022,
        source_project=Path("project.cst"),
        mutable_parameters=frozenset({"fmin"}),
        required_templates=(
            ResultTemplateRequirement("Frequency", "M0D", "Template", "Folder"),
        ),
        native_scalars=(
            NativeScalarCapability(
                "frequency", Path("Frequency") / "Mode 1.rd0", "MHz"
            ),
        ),
        runtime_vba_metrics=frozenset({"dynamic_metric"}),
    )


def test_generic_profile_validates_tasks_inventory_and_classification():
    profile = _profile()
    profile.validate_task(Task.create(new_session_id(), {"fmin": "1"}))
    with pytest.raises(ProfileValidationError, match="unsupported"):
        profile.validate_task(Task.create(new_session_id(), {"unsupported": "1"}))

    record = type(
        "Record",
        (),
        dict(
            result_name="Frequency",
            template_type="M0D",
            template_name="Template",
            folder="Folder",
        ),
    )()
    profile.validate_inventory((record,))
    assert result_classification(profile) == {
        "frequency": "native",
        "dynamic_metric": "runtime-vba",
    }


def test_generic_scalar_reader_is_strict_and_profile_independent(tmp_path):
    capability = NativeScalarCapability(
        "voltage", Path("Voltage") / "Mode 2.rd0", "V"
    )
    path = tmp_path / "Result" / capability.relative_path
    path.parent.mkdir(parents=True)
    path.write_text("2.5", encoding="ascii")

    result = read_native_scalar_results(tmp_path, (capability,))["voltage"]
    assert result.value == 2.5
    assert result.unit == "V"

    path.write_text("1\n2", encoding="ascii")
    with pytest.raises(NativeResultError, match="one scalar line"):
        read_native_scalar_results(tmp_path, (capability,))


def test_generic_provider_selection_has_no_physics_specific_request_type():
    native = select_result_provider(("line", 5), {("line", 5): "native_key"})
    runtime = select_result_provider(("line", 7.5), {("line", 5): "native_key"})

    assert native.provider is ResultProvider.NATIVE
    assert native.native_key == "native_key"
    assert runtime.provider is ResultProvider.RUNTIME_VBA
    assert runtime.native_key is None
