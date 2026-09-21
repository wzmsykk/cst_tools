from pathlib import Path
from dataclasses import replace

import pytest

from csttool.native_results import (
    NativeResultError,
    NativeResultMissingError,
    read_profile_native_results,
    result_classification,
)
from csttool.hom_project_profile import HOM_PROFILE_V1, NativeScalarCapability


def make_result_tree(root, values=None):
    values = values or {}
    for index, spec in enumerate(HOM_PROFILE_V1.native_scalars, start=1):
        path = root / "Result" / spec.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(values.get(spec.key, index)), encoding="ascii")


def test_reads_fixed_hom_native_scalar_set_with_units(tmp_path):
    make_result_tree(tmp_path, {"frequency": 765.981, "q_factor": 229.748})

    results = read_profile_native_results(tmp_path, HOM_PROFILE_V1)
    classification = result_classification(HOM_PROFILE_V1)

    assert results["frequency"].value == 765.981
    assert results["frequency"].unit == "MHz"
    assert results["q_factor"].value == 229.748
    assert results["r_over_q"].unit == "ohm"
    assert all(classification[key] == "native" for key in results)
    assert classification["shunt_impedance"] == "runtime-vba"


def test_missing_empty_multiline_and_nonfinite_results_fail(tmp_path):
    with pytest.raises(NativeResultMissingError, match="missing"):
        read_profile_native_results(tmp_path, HOM_PROFILE_V1)

    make_result_tree(tmp_path)
    frequency = tmp_path / "Result" / HOM_PROFILE_V1.native_scalars[0].relative_path
    frequency.write_text("", encoding="ascii")
    with pytest.raises(NativeResultError, match="one scalar line"):
        read_profile_native_results(tmp_path, HOM_PROFILE_V1)
    frequency.write_text("1\n2", encoding="ascii")
    with pytest.raises(NativeResultError, match="one scalar line"):
        read_profile_native_results(tmp_path, HOM_PROFILE_V1)
    frequency.write_text("nan", encoding="ascii")
    with pytest.raises(NativeResultError, match="not finite"):
        read_profile_native_results(tmp_path, HOM_PROFILE_V1)


def test_reader_and_classification_use_the_supplied_profile(tmp_path):
    custom = replace(
        HOM_PROFILE_V1,
        profile_id="custom-native-test",
        native_scalars=(
            NativeScalarCapability("custom_value", Path("Custom") / "value.rd0", "V"),
        ),
        runtime_vba_metrics=frozenset({"custom_runtime"}),
    )
    path = tmp_path / "Result" / "Custom" / "value.rd0"
    path.parent.mkdir(parents=True)
    path.write_text("12.5", encoding="ascii")

    results = read_profile_native_results(tmp_path, custom)
    classification = result_classification(custom)

    assert tuple(results) == ("custom_value",)
    assert results["custom_value"].value == 12.5
    assert results["custom_value"].unit == "V"
    assert classification == {
        "custom_value": "native",
        "custom_runtime": "runtime-vba",
    }
