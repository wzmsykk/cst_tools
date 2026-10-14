from pathlib import Path
import os
import re
import stat
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
    assert '.SetFrequencyTarget True, RestoreDoubleParameter(""fmin"")' in source
    assert '.SetNumberOfModes CInt(RestoreDoubleParameter(""nmodes""))' in source
    assert '.SetMeshAdaptationTet False' in source
    assert "AKSMaximumDF" not in source
    assert '.Set ""StepsPerWaveNear"", ""cell""' in source
    assert 'AddToHistory "CST Tools: Bind HOM solver parameters", history' in source
    assert source.index("    BindHomSolverSettings") < source.index("    If Not Rebuild")
    assert "Save\n" in source
    assert "    Quit\n" not in source
    assert 'OpenFile(cstProjectPath)' not in source


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


@pytest.mark.parametrize("readonly", [False, True])
def test_preprocessor_creates_distinct_prepared_project_and_parameter_manifest(
    tmp_path, readonly,
):
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    source_project = tmp_path / "source.cst"
    source_project.write_bytes(b"original-project")
    if readonly:
        source_project.chmod(source_project.stat().st_mode & ~stat.S_IWRITE)
    output_project = tmp_path / "prepared.cst"
    parameter_json = tmp_path / "params.json"

    def successful_runner(command, **kwargs):
        assert command[:3] == [str(executable), "-m", "-b"]
        macro = (Path(command[3]).with_suffix('')/'Model'/'3D'/'Model.run').read_text(encoding="utf-8")
        assert "%MESHCELLSPERWAVELENGTH%" not in macro
        assert 'StoreParameter "cell", "24"' in macro
        parameter_output = _macro_path(macro, "paramFileDstPath")
        status_output = _macro_path(macro, "statusFilePath")
        working_project = _macro_path(macro, "cstProjectPath")
        assert working_project != source_project
        assert working_project.stat().st_mode & stat.S_IWRITE
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
    assert output_project.stat().st_mode & stat.S_IWRITE
    assert result.project_path == output_project
    directory, = (tmp_path / "temp").glob("cst-preprocess-*")
    assert (directory / "Model.run").is_file()
    assert not (directory / source_project.name).exists()
    assert not (directory / source_project.stem).exists()
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
        macro = (Path(command[3]).with_suffix('')/'Model'/'3D'/'Model.run').read_text(encoding="utf-8")
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


def test_failed_preprocessing_preserves_copy_macro_and_report(tmp_path):
    import json
    executable = tmp_path / "cst.exe"
    executable.write_bytes(b"fake")
    source = tmp_path / "source.cst"
    source.write_bytes(b"original")
    def failed_runner(command, **kwargs):
        assert kwargs['timeout'] is None
        return subprocess.CompletedProcess(command, 4, "macro failed", "")
    with pytest.raises(CstPreprocessError, match="诊断目录"):
        CstProjectPreprocessor(executable, TEMPLATE, runner=failed_runner).preprocess(
            source, tmp_path / "output.cst", tmp_path / "p.json", tmp_path / "temp")
    directory, = (tmp_path / "temp").glob("cst-preprocess-*")
    assert (directory / "source.cst").read_bytes() == b"original"
    assert (directory / "source/Model/3D/Model.run").is_file()
    assert (directory / "runner-output.txt").read_text() == "macro failed"
    assert json.loads((directory / "preprocess-report.json").read_text(encoding="utf-8"))['state'] == 'failed'
    assert not (tmp_path / "output.cst").exists()


def test_native_runner_uses_stage_monitor_without_communicate_timeout(tmp_path, monkeypatch):
    import csttool.cst_preprocessor as module
    class Process:
        pid = 123
        returncode = 0
    baseline = [{'pid':99, 'create_time':99., 'name':'independent CST'}]
    observed = []
    monkeypatch.setattr(module, 'cst_processes', lambda:observed.append('baseline') or baseline)
    def launch(*args, **kwargs):
        assert observed == ['baseline']
        return Process()
    monkeypatch.setattr(module.subprocess, 'Popen', launch)
    from types import SimpleNamespace
    monkeypatch.setattr(module.psutil, 'Process', lambda pid:SimpleNamespace(create_time=lambda:1.))
    def monitor(process, directory, **kwargs):
        assert kwargs['completion_names'] == ('completion.txt',)
        assert {'bind-history', 'rebuild', 'save'} <= set(kwargs['unbounded_stages'])
        assert kwargs['stage_timeout'] == 180
        assert kwargs['preexisting_processes'] == baseline
        assert kwargs['task_project'] == str(tmp_path/'model.cst')
        return {'foreign_processes': [{'pid':88,'create_time':88.}]}
    monkeypatch.setattr(module, 'wait_probe', monitor)
    assert CstProjectPreprocessor(tmp_path / 'cst.exe', TEMPLATE)._run(['fake','-m','-b',str(tmp_path/'model.cst')], tmp_path).returncode == 0


def test_previous_live_preprocess_blocks_retry_without_launch(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import csttool.cst_preprocessor as module
    executable = tmp_path / 'cst.exe'
    executable.write_bytes(b'fake')
    source = tmp_path / 'source.cst'
    source.write_bytes(b'original')
    old = tmp_path / 'temp/cst-preprocess-old'
    old.mkdir(parents=True)
    (old / 'session-status.json').write_text(json.dumps({'owned':[{'pid':1, 'create_time':2.}]}))
    monkeypatch.setattr(module.psutil, 'Process', lambda pid:SimpleNamespace(
        create_time=lambda:2., is_running=lambda:True))
    def forbidden(*args, **kwargs):
        pytest.fail('must not launch competing CST')
    with pytest.raises(CstPreprocessError, match='仍活跃'):
        CstProjectPreprocessor(executable, TEMPLATE, runner=forbidden).preprocess(
            source, tmp_path / 'output.cst', tmp_path / 'p.json', tmp_path / 'temp')


def test_detail_journal_logs_complete_lines_once_and_stage_changes(tmp_path, caplog):
    import logging
    processor = CstProjectPreprocessor(tmp_path / 'cst.exe', TEMPLATE)
    cursor = [0]
    observe = processor._observer(tmp_path, cursor)
    journal = tmp_path / 'changes.tsv'
    complete = 'now\tparameter-set\tcell\t2 * density\t24\trequested\n'
    journal.write_text(complete + 'now\tstage\trebuild', encoding='utf-8')
    with caplog.at_level(logging.INFO):
        observe({'stage':'rebuild', 'elapsed_seconds':1.})
        observe({'stage':'rebuild', 'elapsed_seconds':31.})
        journal.write_text(complete + 'now\tstage\trebuild\t\t\treturned-success\n', encoding='utf-8')
        observe({'stage':'save', 'elapsed_seconds':32.})
        processor._log_details(tmp_path, cursor)
    assert cursor == [2]
    changes = [record for record in caplog.records if getattr(record, 'action', '') == 'parameter-set']
    assert len(changes) == 1
    assert changes[0].before == '2 * density' and changes[0].after == '24'
    assert changes[0].status == 'requested'
    assert caplog.text.count('预处理进入阶段') == 2
    assert 'returned-success' in caplog.text


def test_macro_details_use_documented_parameter_index_not_name():
    source = TEMPLATE.read_text(encoding='utf-8-sig')
    assert 'GetParameterSValue(parameterIndex)' in source
    assert 'GetParameterSValue("' not in source
    assert 'ParameterExpression("fmin")' in source
    assert '"<not-read>", history, "requested"' in source
    assert '"returned-not-verified"' in source
    assert source.index('failureNumber = Err.Number') < source.index('WriteDetail "error"')


def test_preserve_mesh_accepts_project_without_cell(tmp_path):
    executable = tmp_path / 'cst.exe'
    executable.write_bytes(b'fake')
    source = tmp_path / 'source.cst'
    source.write_bytes(b'original')
    def runner(command, **kwargs):
        macro = (Path(command[3]).with_suffix('') / 'Model/3D/Model.run').read_text(encoding='utf-8')
        assert 'modifyMesh = False' in macro
        assert 'If Not modifyMesh Then' in macro
        assert 'If modifyMesh Then history = history & ".SetMeshAdaptationTet False"' in macro
        _macro_path(macro, 'statusFilePath').write_text('SUCCESS')
        _macro_path(macro, 'paramFileDstPath').write_text(
            'parameters\nproject\n3\n0 fmin 500 min\n1 fmax 700 max\n2 nmodes 1 modes\n')
        return subprocess.CompletedProcess(command, 0, '', '')
    result = CstProjectPreprocessor(executable, TEMPLATE, runner=runner).preprocess(
        source, tmp_path / 'prepared.cst', tmp_path / 'p.json', tmp_path / 'temp', modify_mesh=False)
    assert {p['name'] for p in result.parameters} == {'fmin','fmax','nmodes'}


def test_old_foreign_receipt_does_not_block_retry(tmp_path):
    import json
    import psutil
    executable = tmp_path/'cst.exe'
    executable.write_bytes(b'fake')
    source = tmp_path/'source.cst'
    source.write_bytes(b'original')
    receipt = tmp_path/'temp/cst-preprocess-old/session-status.json'
    receipt.parent.mkdir(parents=True)
    identity = psutil.Process()
    receipt.write_text(json.dumps({'owned':[], 'foreign_processes':[
        {'pid':identity.pid, 'create_time':identity.create_time()}]}))
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, '', '')
    with pytest.raises(CstPreprocessError, match='未返回完成状态'):
        CstProjectPreprocessor(executable,TEMPLATE,runner=runner).preprocess(
            source,tmp_path/'prepared.cst',tmp_path/'p.json',tmp_path/'temp')
    assert len(calls) == 1
