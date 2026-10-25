"""Static semantic guards; real CST acceptance remains separately required."""
from pathlib import Path

import pytest

DATA = Path(__file__).parents[1] / 'data'


@pytest.mark.parametrize('name', ['runtime_managed_worker_v1_main.vb',
                                 'runtime_worker_v1_main.vb', 'runtime_warm_worker_v1_main.vb'])
def test_solver_return_and_integer_mode_count(name):
    source = (DATA / name).read_text()
    if name == 'runtime_managed_worker_v1_main.vb':
        assert 'solverReturn = EigenmodeSolver.Start' in source
        assert 'If solverReturn <> 1 Then' in source
        assert '"SOLVER_FAILED", "EigenmodeSolver.Start returned " & CStr(solverReturn)' in source
    else:
        assert 'If EigenmodeSolver.Start <> 1 Then' in source
        assert '"SOLVER_FAILED", "EigenmodeSolver.Start returned 0"' in source
    assert 'requestedModes <> Fix(requestedModes)' in source
    assert 'SetNumberOfModes CInt(requestedModes)' in source
    assert 'requestedModes = RestoreDoubleParameter("nmodes")' in source


def test_managed_solver_configuration_is_not_a_start_exception():
    source = (DATA / 'runtime_managed_worker_v1_main.vb').read_text()
    assert source.index('stage = "solver-config"') < source.index('requestedModes =')
    assert source.index('stage = "solver-start"') < source.index('solverReturn =')
    assert 'If stage = "solver-start" Or stage = "solver-result" Then' in source
    assert 'ElseIf stage = "rebuild" Then\n        errorCode = "REBUILD_FAILED"' in source
    assert '"returned=" & CStr(solverReturn)' in source


def test_managed_start_success_requires_available_modes():
    source = (DATA / 'runtime_managed_worker_v1_main.vb').read_text()
    assert source.index('stage = "solver-result"') < source.index('stage = "postprocess"')
    assert 'EigenmodeSolver.GetNumberOfModesCalculated < 1' in source
    assert 'no eigenmodes are available' in source


def test_preprocess_checks_rebuild_and_typed_history():
    source = (DATA / 'preprocess_hom_parameters_v1.vb').read_text()
    assert 'If Not Rebuild Then Err.Raise' in source
    assert '.SetMeshAdaptationTet False' in source
    assert '.SetFrequencyTarget True, RestoreDoubleParameter(' in source


def test_missing_complex_result_is_not_zero():
    source = (DATA / 'postprocess/EigenResult_Complex.vb').read_text()
    start = source.split('Function EigenResult_Complex(')[1].split('With QFactor')[0]
    assert 'Exit Function' not in start
    assert 'Err.Raise' in start


def test_application_scope_not_silently_enabled():
    source = Path('test/support/benchmark_field_efficiency.py').read_text()
    assert "raise ValueError('Application entry disabled:" in source
    assert 'GetObject(' not in source


def test_managed_restore_uses_exact_sized_expression_batch_and_stage_pairs():
    from pathlib import Path
    macro = Path('data/runtime_managed_worker_v1_main.vb').read_text(encoding='ascii')
    restore = macro.split('Private Sub CSTPMW_RestoreGoodParameters', 1)[1].split('Private Sub CSTPMW_Trace', 1)[0]
    assert 'If restored > 0 Then' in restore
    assert 'ReDim names(0 To restored - 1), expressions(0 To restored - 1)' in restore
    assert 'expressions(slot) = goodParameterExpressions(index)' in restore
    assert 'StoreParameters(names, expressions)' in restore
    assert 'StoreParameter ' not in restore
    assert 'For index = appliedParameterCount - 1 To 0 Step -1' in restore
    assert restore.index('StoreParameters(') < restore.index('DeleteParameter goodParameterNames(index)')
    assert 'Restored expression mismatch:' in restore
    for stage in ('restore-batch', 'restore-delete'):
        assert f'"{stage}", "%PROJECT_PATH%", "begin' in restore
        assert f'"{stage}", "%PROJECT_PATH%", "returned' in restore
    for stage, path in (('recovery-snapshot','%PROJECT_PATH%.recovered.cst'),
                        ('close-receipt','%CLOSE_RECEIPT_PATH%'), ('stop-ack','%STOP_ACK_PATH%')):
        block = macro.split(f'closeStage = "{stage}"',1)[1]
        assert f'CSTPMW_Trace closeStage, "{path}", "begin' in block
        assert f'CSTPMW_Trace closeStage, "{path}", "returned' in block


def test_task_undo_captures_before_mutation_without_full_project_enumeration():
    from pathlib import Path
    source = Path('data/runtime_managed_worker_v1_main.vb').read_text(encoding='ascii')
    capture = source.split('Private Sub CSTPMW_CaptureTaskParameters',1)[1].split('End Sub',1)[0]
    assert 'DoesParameterExist(name)' in capture
    assert 'RestoreParameterExpression(name)' in capture
    assert 'If Not existed Or expression <> task.Parameters(index).Value Then' in capture
    assert 'Duplicate task parameter:' in capture
    assert capture.index('Close #f') < capture.index('goodParametersAvailable = True')
    assert 'CST_PARAMETER_UNDO_V2' in capture and 'task.TaskId' in capture
    assert 'GetNumberOfParameters' not in source and 'GetParameterName(' not in source
    assert source.count('CSTPMW_CaptureTaskParameters task') == 1
    main = source.split('Private Sub CSTPMW_CheckStop',1)[0]
    assert main.index('CSTPMW_CaptureTaskParameters task') < main.index('modelNeedsRecovery = True')
    assert main.index('appliedParameterCount = i + 1') < main.index('StoreParameter goodParameterNames(i)')
    success = main.split('stage = "flush"',1)[1].split('WaitForAck:',1)[0]
    assert 'goodParametersAvailable = False' in success
    assert 'CaptureTaskParameters' not in success
    restore = source.split('Private Sub CSTPMW_RestoreGoodParameters',1)[1].split('Private Sub CSTPMW_Trace',1)[0]
    assert 'If Not goodParameterExists(index) Then' in restore
    assert 'Added parameter still exists:' in restore
    close = source.split('Private Sub CSTPMW_CloseSession',1)[1].split('CloseFailed:',1)[0]
    assert close.index('If activeTaskSolveReady Or solverReturnedSuccess Then') < close.index('CSTPMW_RestoreGoodParameters')
