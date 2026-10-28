"""Safety/reporting checks for the optional real-CST calibration probe."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    'settings_calibration_probe', Path(__file__).parent / 'support/calibrate_cst_settings.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_query_only_reopen_cannot_apply_history_or_start_solver(tmp_path):
    macro = probe.render(tmp_path, probe.cases(), reopen=True)
    assert 'AddToHistory(' not in macro
    assert 'EigenmodeSolver.Set' not in macro
    assert 'EigenmodeSolver.Start' not in macro
    assert 'Backup ' not in macro
    assert 'GetParameterSValue' in macro


def test_unrecognized_case_rejected_before_any_cst_session(monkeypatch):
    monkeypatch.setattr('sys.argv', ['probe', '--cst-exe', 'unused.exe', '--case', 'typo'])
    monkeypatch.setattr(probe, 'exclusive_probe', lambda *_: pytest.fail('session acquired'))
    with pytest.raises(SystemExit, match='2'):
        probe.main()


def test_expression_damage_fails_even_after_normal_process_exit(tmp_path, monkeypatch):
    (tmp_path / 'completed.txt').write_text('SUCCESS')
    (tmp_path / 'expressions.tsv').write_text('before\tL\t2*R\nafter\tL\t20\n')
    monkeypatch.setattr(probe.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(probe, 'wait_probe', lambda *a, **k: {'exit_confirmed': True})
    with pytest.raises(RuntimeError, match='did not complete normally'):
        probe.run(Path('unused.exe'), tmp_path / 'copy.cst', tmp_path, 'macro')
    assert json.loads((tmp_path / 'report.json').read_text())['expressions_preserved'] is False
