import pytest

from csttool.hom_result_plan import (
    HomRoverQRequest,
    ResultProvider,
    ResultTemplatePhase,
    UnsafeResultTemplateChange,
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


def test_arbitrary_hom_integral_line_keeps_runtime_vba():
    plan = plan_hom_r_over_q(HomRoverQRequest("z", 0, 7.5))
    assert plan.provider is ResultProvider.RUNTIME_VBA
    assert plan.native_key is None


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
