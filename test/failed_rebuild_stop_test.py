from pathlib import Path
from types import SimpleNamespace
import logging

import pytest
from csttool.managed_cstworker import ManagedCSTWorker


@pytest.mark.parametrize('code,receipt,snapshot,expected', [
    (0, None, b'', True), (4, None, b'valid', False),
    (4, 'CST_RECOVERY_SAVED_V1\nwrong-session\n', b'valid', False),
    (4, 'CST_RECOVERY_SAVED_V1\nsession\n', b'', False),
    (4, 'CST_RECOVERY_SAVED_V1\nsession\n', b'valid', True),
    (1, 'CST_RECOVERY_SAVED_V1\nsession\n', b'valid', False),
    (4, 'invalid-非ASCII\n', b'valid', False),
])
def test_nonzero_exit_requires_own_saved_recovery(tmp_path, code, receipt, snapshot, expected):
    worker = object.__new__(ManagedCSTWorker)
    worker._process = SimpleNamespace(poll=lambda: code)
    worker.session_id = 'session'
    worker.project_path = tmp_path / 'worker-input.cst'
    worker.logger = logging.getLogger('recovery-test')
    if receipt:
        Path(str(worker.project_path) + '.recovery-saved').write_text(receipt)
    Path(str(worker.project_path) + '.recovered.cst').write_bytes(snapshot)
    assert worker._stop_exit_is_confirmed() is expected


def test_recovery_keeps_expressions_and_never_replays_solver():
    source = Path('data/runtime_managed_worker_v1_main.vb').read_text()
    close = source.split('Private Sub CSTPMW_CloseSession', 1)[1].split('End Sub', 1)[0]
    assert close.index('CSTPMW_RestoreGoodParameters') < close.index('If Not Rebuild') < close.index('\n    Save\n') < close.index('CSTP_WriteStopAck')
    assert 'EigenmodeSolver.Start' not in close and '\n    Quit\n' not in close
    assert close.index('\n    Save\n') < close.index('CST_RECOVERY_SAVED_V1')
    capture = source.split('Private Sub CSTPMW_CaptureTaskParameters', 1)[1].split('End Sub', 1)[0]
    assert 'RestoreParameterExpression' in capture and 'RestoreDoubleParameter' not in capture


def test_recovery_snapshot_is_checked_before_save_receipt_and_stop_ack():
    source = Path('data/runtime_managed_worker_v1_main.vb').read_text()
    close = source.split('Private Sub CSTPMW_CloseSession', 1)[1].split('End Sub', 1)[0]
    assert close.index('If FileLen(') < close.index('CST_RECOVERY_SAVED_V1') < close.index('CSTP_WriteStopAck')
    failure = close.split('CloseFailed:', 1)[1]
    assert 'CSTP_WriteStopAck' not in failure
    assert 'failure:' in failure and 'number=' in failure


def test_fault_probe_uses_real_conditions_not_mocked_rebuild():
    source = Path('test/support/validate_recovery_faults.py').read_text()
    assert 'StoreParameter "nmodes", "0"' in source
    assert 'blocker.mkdir()' in source
    assert 'report[\'stop_rejected\'] and not report[\'stop_ack\']' in source


@pytest.mark.parametrize('alive', [True, None])
def test_fault_reconciliation_never_abandons_live_or_unknown_process(tmp_path, monkeypatch, alive):
    from test.support import validate_recovery_faults as probe
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    root = tmp_path / 'artifacts' / 'case'
    root.mkdir(parents=True)
    (root / 'report.json').write_text('{"gate_passed": true}')
    monkeypatch.setattr(probe, 'discover_managed_sessions', lambda root: [SimpleNamespace(process_alive=alive)])
    def must_not_recover(root):
        pytest.fail('must not reconcile live or unidentified process')
    monkeypatch.setattr(probe, 'recover_project_sessions', must_not_recover)
    with pytest.raises(AssertionError):
        probe.reconcile_report(root)
