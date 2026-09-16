from dataclasses import replace

import pytest

from csttool.hom_project_profile import HOM_PROFILE_V1, NativeRoverQCapability
from csttool.hom_result_plan import (
    HomRoverQRequest,
    IntegrationLine,
    ResultProvider,
    ResultTemplatePhase,
    UnsafeResultTemplateChange,
    integration_line_from_template_settings,
    native_r_over_q_for_profile,
    plan_hom_r_over_q,
    validate_result_template_change,
)


@pytest.mark.parametrize(
    ("yoffset", "key"),
    [(0, "r_over_q"), (5, "r_over_q_offset_5mm"), (10, "r_over_q_offset_10mm")],
)
def test_predefined_hom_integral_lines_use_native_results(yoffset, key):
    plan = plan_hom_r_over_q(HomRoverQRequest("z", 0, yoffset))
    assert plan.provider is ResultProvider.NATIVE
    assert plan.native_key == key


@pytest.mark.parametrize(
    ("coordinate", "expected"),
    [
        ("0", IntegrationLine("x", yoffset_mm=2, zoffset_mm=3)),
        ("1", IntegrationLine("y", xoffset_mm=1, zoffset_mm=3)),
        ("2", IntegrationLine("z", xoffset_mm=1, yoffset_mm=2)),
    ],
)
def test_official_template_coordinates_support_every_axis(coordinate, expected):
    line = integration_line_from_template_settings(
        {
            "coordinates": coordinate,
            "maxrange": "1",
            "u1": "1",
            "v1": "2",
            "w1": "3",
        }
    )
    assert line == expected
    plan = plan_hom_r_over_q(line, {line: f"native_{line.axis}"})
    assert plan.provider is ResultProvider.NATIVE
    assert plan.native_key == f"native_{line.axis}"


@pytest.mark.parametrize(
    "line",
    [
        IntegrationLine("x", yoffset_mm=5),
        IntegrationLine("y", xoffset_mm=5),
        IntegrationLine("z", yoffset_mm=7.5),
    ],
)
def test_unregistered_integral_lines_keep_runtime_vba(line):
    plan = plan_hom_r_over_q(line)
    assert plan.provider is ResultProvider.RUNTIME_VBA
    assert plan.native_key is None


def test_r_over_q_routing_uses_the_supplied_profile():
    custom_line = IntegrationLine("x", yoffset_mm=3)
    custom = replace(
        HOM_PROFILE_V1,
        profile_id="custom-routing-test",
        native_r_over_q=(
            NativeRoverQCapability("x", 0, 3, 0, "custom_native_r_over_q"),
        ),
    )

    assert native_r_over_q_for_profile(custom) == {
        custom_line: "custom_native_r_over_q"
    }
    custom_plan = plan_hom_r_over_q(custom_line, profile=custom)
    default_line_plan = plan_hom_r_over_q(IntegrationLine("z"), profile=custom)

    assert custom_plan.provider is ResultProvider.NATIVE
    assert custom_plan.native_key == "custom_native_r_over_q"
    assert default_line_plan.provider is ResultProvider.RUNTIME_VBA


def test_r_over_q_routing_rejects_two_capability_sources():
    line = IntegrationLine("z")
    with pytest.raises(ValueError, match="either native_results or profile"):
        plan_hom_r_over_q(line, {line: "native"}, profile=HOM_PROFILE_V1)


def test_integration_axis_and_offsets_are_validated():
    with pytest.raises(ValueError, match="x, y, or z"):
        IntegrationLine("bad")
    with pytest.raises(ValueError, match="along the integration axis"):
        IntegrationLine("x", xoffset_mm=1)
    with pytest.raises(ValueError, match="resolved numeric"):
        integration_line_from_template_settings(
            {"coordinates": "0", "maxrange": "1", "v1": "parameter_name"}
        )


def test_post_solve_template_change_cannot_update_project_parameters():
    with pytest.raises(UnsafeResultTemplateChange, match="invalidates solved results"):
        validate_result_template_change(
            ResultTemplatePhase.AFTER_SOLVE, changes_project_parameters=True
        )
    validate_result_template_change(
        ResultTemplatePhase.AFTER_SOLVE, changes_project_parameters=False
    )
    validate_result_template_change(
        ResultTemplatePhase.BEFORE_SOLVE, changes_project_parameters=True
    )
