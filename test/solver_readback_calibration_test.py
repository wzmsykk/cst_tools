"""Safety boundaries of the optional V01/V02/V04 acceptance probe."""
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent / 'support'))
    return importlib.import_module('calibrate_solver_readback')


def test_solve_requires_explicit_single_case_before_acquiring_cst(probe, monkeypatch):
    monkeypatch.setattr('sys.argv', ['probe', '--cst-exe', 'unused.exe', '--solve'])
    monkeypatch.setattr(probe.probe, 'exclusive_probe', lambda *_: pytest.fail('CST session acquired'))
    with pytest.raises(SystemExit, match='2'):
        probe.main()


def test_query_only_snapshot_reopen_has_no_solver_or_setting_write(probe, tmp_path):
    macro = probe.render(tmp_path, probe.cases(), reopen=True)
    assert 'AddToHistory(' not in macro and 'EigenmodeSolver.Start' not in macro
    assert 'EigenmodeSolver.Set' not in macro
    assert 'ERROR:' in macro and 'GetDataBaseValue(key)' in macro


def test_stale_probe_changes_request_but_never_recomputes_or_flattens_parameters(probe, tmp_path):
    macro = probe.render_staleness(tmp_path)
    assert 'EigenmodeSolver.Start' not in macro
    assert 'StoreParameter' not in macro
    assert 'EigenmodeSolver.SetNumberOfModes 2' in macro
    assert 'after-rebuild' in macro and 'If Not Rebuild Then' in macro


def test_scalar_readback_probe_does_not_enable_solve_implicitly(probe, tmp_path):
    macro = probe.render(tmp_path, probe.cases())
    assert 'EigenmodeSolver.Start' not in macro
    assert len(probe.keys()) == 22
    assert probe.keys()[-1] == 'CSTToolsCalibrationMissingKey'
