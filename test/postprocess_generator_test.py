import json
from pathlib import Path

import pytest

from csttool.postprocess_cst import CstPostProcessor


DATA_DIR = Path(__file__).parents[1] / "data"


def load_settings(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("config_name", "expected_steps"),
    [("defaultPPS.json", 7), ("TM020PPS.json", 6), ("WTCPPS.json", 11)],
)
def test_shipped_pps_configs_compile(config_name, expected_steps):
    processor = CstPostProcessor()

    processor.configure(load_settings(config_name))
    generated = "".join(processor.render_vb())

    assert len(processor.postProcessDocList) == expected_steps
    assert generated.count("Sub CustomPostProcess") == 1
    assert generated.rstrip().endswith("End Sub")


def test_tm020_generation_preserves_existing_calls_and_filenames():
    processor = CstPostProcessor()
    processor.configure(load_settings("TM020PPS.json"))

    steps = processor.postProcessDocList

    assert steps[0]["resultFilename"] == "Frequency_All_frequency.txt"
    assert steps[0]["funcString"] == (
        'EigenResult_Simple_All_output("Frequency",outFullDir,'
        '"Frequency_All_frequency.txt")\n'
    )
    assert steps[1]["resultFilename"] == (
        "ROQ_All_xoffset_0.000000_yoffset_0.000000_R_divide_Q.txt"
    )
    assert steps[2]["resultFilename"] == (
        "SI_All_xoffset_0.000000_yoffset_0.000000_Shunt_Impedance.txt"
    )
    assert steps[-1]["funcString"] == "ModeRec_All_output(outFullDir)\n"


def test_vba_imports_are_deduplicated_in_first_use_order():
    processor = CstPostProcessor()
    processor.configure(load_settings("TM020PPS.json"))

    generated = "".join(processor.render_vb())

    assert generated.count("Function EigenResult_Simple(") == 1
    assert generated.count("Const lib_rundef") == 1
    assert generated.index("Function EigenResult_Simple(") < generated.index(
        "Const lib_rundef"
    )


def test_duplicate_output_names_get_unique_filenames():
    processor = CstPostProcessor()
    setting = {
        "method": "Frequency",
        "resultName": "frequency",
        "params": {"iModeNumber": 1},
    }

    processor.configure([setting, setting, setting])

    assert processor.getUsedFileNameList() == [
        "Mode_1_Frequency_frequency.txt",
        "Mode_1_Frequency_frequency_0.txt",
        "Mode_1_Frequency_frequency_1.txt",
    ]


def test_unknown_method_and_missing_parameter_fail_early():
    processor = CstPostProcessor()

    with pytest.raises(ValueError, match="Unsupported PPS method"):
        processor.configure(
            [{"method": "Unknown", "resultName": "x", "params": {}}]
        )
    with pytest.raises(ValueError, match="iModeNumber"):
        processor.configure(
            [{"method": "Frequency", "resultName": "x", "params": {}}]
        )


@pytest.mark.parametrize(
    ("axis", "offsets", "axis_number"),
    [
        ("x", {"xoffset": 1, "yoffset": 2, "zoffset": 3}, 1),
        ("y", {"xoffset": 1, "yoffset": 2, "zoffset": 3}, 2),
        ("z", {"xoffset": 1, "yoffset": 2, "zoffset": 3}, 3),
    ],
)
def test_complex_pps_generation_supports_every_axis(axis, offsets, axis_number):
    processor = CstPostProcessor()
    processor.configure(
        [
            {
                "method": "R_over_Q",
                "resultName": f"roq_{axis}",
                "params": {"iModeNumber": 1, "axis": axis, **offsets},
            }
        ]
    )

    step = processor.postProcessDocList[0]
    assert step["params"]["axis"] == axis
    for key, value in offsets.items():
        assert step["params"][key] == value
    assert f'{axis_number},1,2,3,' in step["funcString"]
    assert (
        f'EigenResult_Complex_output(1,"R over Q",{axis_number},'
        in step["funcString"]
    )
    assert f"_axis_{axis}_" in step["resultFilename"] or axis == "z"


def test_scalar_and_all_mode_results_are_parsed(tmp_path):
    processor = CstPostProcessor()
    processor.set_result_directory(tmp_path)
    processor.configure(
        [
            {
                "method": "Frequency",
                "resultName": "single",
                "params": {"iModeNumber": 1},
            },
            {"method": "Frequency_All", "resultName": "all", "params": {}},
        ]
    )
    (tmp_path / processor.postProcessDocList[0]["resultFilename"]).write_text(
        "Result Name\nEigenResult_Simple\nvalue\n500.25\n",
        encoding="utf-8",
    )
    (tmp_path / processor.postProcessDocList[1]["resultFilename"]).write_text(
        "ModeIndex 1\n500.25\nModeIndex 2\n700.5\n",
        encoding="utf-8",
    )

    results = processor.read_all_results()

    assert results[0]["value"] == 500.25
    assert results[1]["value"] == {"ModeIndex 1": 500.25, "ModeIndex 2": 700.5}
