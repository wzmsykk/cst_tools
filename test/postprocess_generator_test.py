import json
from pathlib import Path

import pytest

from csttool.postprocess_cst import VBPostProcessor, vbpostprocess


DATA_DIR = Path(__file__).parents[1] / "data"


def load_settings(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("config_name", "expected_steps"),
    [("defaultPPS.json", 7), ("TM020PPS.json", 6), ("WTCPPS.json", 11)],
)
def test_shipped_pps_configs_compile(config_name, expected_steps):
    processor = VBPostProcessor()

    processor.appendPostProcessSteps(load_settings(config_name))
    generated = "".join(processor.createPostProcessVBCodeLines())

    assert len(processor.postProcessDocList) == expected_steps
    assert generated.count("Sub CustomPostProcess") == 1
    assert generated.rstrip().endswith("End Sub")


def test_tm020_generation_preserves_existing_calls_and_filenames():
    processor = VBPostProcessor()
    processor.appendPostProcessSteps(load_settings("TM020PPS.json"))

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
        "SI_All_xoffset_0.000000_yoffset_0.000000_Shunt_Inpedence.txt"
    )
    assert steps[-1]["funcString"] == "ModeRec_All_output(outFullDir)\n"


def test_vba_imports_are_deduplicated_in_first_use_order():
    processor = VBPostProcessor()
    processor.appendPostProcessSteps(load_settings("TM020PPS.json"))

    generated = "".join(processor.createPostProcessVBCodeLines())

    assert generated.count("Function EigenResult_Simple(") == 1
    assert generated.count("Const lib_rundef") == 1
    assert generated.index("Function EigenResult_Simple(") < generated.index(
        "Const lib_rundef"
    )


def test_duplicate_output_names_get_unique_filenames():
    processor = VBPostProcessor()
    setting = {
        "method": "Frequency",
        "resultName": "frequency",
        "params": {"iModeNumber": 1},
    }

    processor.appendPostProcessSteps([setting, setting, setting])

    assert processor.getUsedFileNameList() == [
        "Mode_1_Frequency_frequency.txt",
        "Mode_1_Frequency_frequency_0.txt",
        "Mode_1_Frequency_frequency_1.txt",
    ]


def test_unknown_method_and_missing_parameter_fail_early():
    processor = VBPostProcessor()

    with pytest.raises(ValueError, match="Unsupported PPS method"):
        processor.appendPostProcessSteps(
            [{"method": "Unknown", "resultName": "x", "params": {}}]
        )
    with pytest.raises(ValueError, match="iModeNumber"):
        processor.appendPostProcessSteps(
            [{"method": "Frequency", "resultName": "x", "params": {}}]
        )


def test_scalar_and_all_mode_results_are_parsed(tmp_path):
    processor = VBPostProcessor()
    processor.setResultDir(tmp_path)
    processor.appendPostProcessSteps(
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

    results = processor.readAllResults()

    assert results[0]["value"] == 500.25
    assert results[1]["value"] == {"ModeIndex 1": 500.25, "ModeIndex 2": 700.5}


def test_historical_class_name_is_preserved():
    assert vbpostprocess is VBPostProcessor
