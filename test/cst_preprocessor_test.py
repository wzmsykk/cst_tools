from pathlib import Path
import os
import re
import subprocess

import pytest

from csttool.cst_preprocessor import CstPreprocessError, CstProjectPreprocessor


TEMPLATE = Path(__file__).parents[1] / "data" / "preprocess_hom_parameters_v1.vb"


def _macro_path(source, variable):
    match = re.search(rf'^\s*{variable} = "(.*)"$', source, re.MULTILINE)
    assert match is not None
    return Path(match.group(1).replace("\\\\", "\\"))


def test_macro_adds_missing_parameters_binds_solver_and_saves():
    source = TEMPLATE.read_text(encoding="utf-8-sig")

    assert 'DoesParameterExist("fmin")' in source
    assert 'DoesParameterExist("fmax")' in source
    assert 'DoesParameterExist("nmodes")' in source
    assert 'DoesParameterExist("cell")' in source
    assert 'history = "Solver.FrequencyRange ""fmin"", ""fmax"""' in source
    assert '.SetFrequencyTarget ""True"", ""fmin""' in source
    assert '.SetNumberOfModes ""nmodes""' in source
    assert '.SetMeshAdaptationTet ""False""' in source
    assert "AKSMaximumDF" not in source
    assert '.Set ""StepsPerWaveNear"", ""cell""' in source
    assert 'AddToHistory "CST Tools: Bind HOM solver parameters", history' in source
    assert source.index("    BindHomSolverSettings") < source.index("    Rebuild")
    assert "Save\n" in source
    assert "Quit\n" in source


def test_preprocessor_starts_cst_minimized_without_activation_on_windows(tmp_path):
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    processor = CstProjectPreprocessor(executable, TEMPLATE)

    options = processor._startup_options()

    if os.name == "nt":
        startupinfo = options["startupinfo"]
        assert startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert startupinfo.wShowWindow == 7
        assert options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert options == {}


def test_preprocessor_can_explicitly_leave_cst_interactive(tmp_path):
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    processor = CstProjectPreprocessor(
        executable, TEMPLATE, run_in_background=False
    )

    options = processor._startup_options()

    if os.name == "nt":
        assert "startupinfo" not in options
        assert options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert options == {}


def test_preprocessor_creates_distinct_prepared_project_and_parameter_manifest(
    tmp_path,
):
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    source_project = tmp_path / "source.cst"
    source_project.write_bytes(b"original-project")
    output_project = tmp_path / "prepared.cst"
    parameter_json = tmp_path / "params.json"

    def successful_runner(command, **kwargs):
        assert command[:2] == [str(executable), "-m"]
        macro = Path(command[2]).read_text(encoding="utf-8")
        assert "%MESHCELLSPERWAVELENGTH%" not in macro
        assert 'StoreParameter "cell", "24"' in macro
        parameter_output = _macro_path(macro, "paramFileDstPath")
        status_output = _macro_path(macro, "statusFilePath")
        working_project = _macro_path(macro, "cstProjectPath")
        assert working_project != source_project
        status_output.write_text("SUCCESS\n", encoding="utf-8")
        parameter_output.write_text(
            "parameters\nproject\n4\n"
            "0 fmin 500 Minimum_frequency\n"
            "1 fmax 700 Maximum_frequency\n"
            "2 nmodes 1 Number_of_modes\n"
            "3 cell 24 Cells_per_wavelength\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    result = CstProjectPreprocessor(
        executable,
        TEMPLATE,
        runner=successful_runner,
    ).preprocess(
        source_project,
        output_project,
        parameter_json,
        tmp_path / "temp",
        mesh_cells_per_wavelength=24,
    )

    assert source_project.read_bytes() == b"original-project"
    assert output_project.read_bytes() == b"original-project"
    assert result.project_path == output_project
    assert [item["name"] for item in result.parameters] == [
        "fmin",
        "fmax",
        "nmodes",
        "cell",
    ]


def test_preprocessor_refuses_in_place_or_existing_output(tmp_path):
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    source = tmp_path / "source.cst"
    source.write_bytes(b"source")
    processor = CstProjectPreprocessor(executable, TEMPLATE)

    with pytest.raises(ValueError, match="distinct output"):
        processor.preprocess(source, source, tmp_path / "p.json", tmp_path / "temp")

    output = tmp_path / "output.cst"
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        processor.preprocess(source, output, tmp_path / "p.json", tmp_path / "temp")


def test_preprocessor_requires_explicit_success_marker(tmp_path):
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    source = tmp_path / "source.cst"
    source.write_bytes(b"source")

    def runner_without_completion(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "", "")

    processor = CstProjectPreprocessor(
        executable,
        TEMPLATE,
        runner=runner_without_completion,
    )
    with pytest.raises(CstPreprocessError, match="未返回完成状态"):
        processor.preprocess(
            source,
            tmp_path / "output.cst",
            tmp_path / "p.json",
            tmp_path / "temp",
        )


def test_preprocessor_does_not_publish_project_with_missing_parameters(tmp_path):
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    source = tmp_path / "source.cst"
    source.write_bytes(b"source")
    output = tmp_path / "output.cst"

    def incomplete_runner(command, **kwargs):
        macro = Path(command[2]).read_text(encoding="utf-8")
        parameter_output = _macro_path(macro, "paramFileDstPath")
        status_output = _macro_path(macro, "statusFilePath")
        status_output.write_text("SUCCESS\n", encoding="utf-8")
        parameter_output.write_text(
            "parameters\nproject\n1\n0 fmin 500 Minimum_frequency\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    processor = CstProjectPreprocessor(
        executable,
        TEMPLATE,
        runner=incomplete_runner,
    )
    with pytest.raises(CstPreprocessError, match="cell, fmax, nmodes"):
        processor.preprocess(
            source,
            output,
            tmp_path / "p.json",
            tmp_path / "temp",
        )
    assert not output.exists()
