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
