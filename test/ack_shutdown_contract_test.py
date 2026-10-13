"""Generated VBA contract checks; not WinWrap runtime acceptance."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from csttool.managed_cstworker import ManagedWorkerShutdownError
from test.managed_cstworker_test import build_worker_shell


ROOT = Path(__file__).parents[1]


def test_open_retry_is_bounded_and_does_not_retry_invalid_protocol():
    codec = (ROOT / 'data/runtime_protocol_v1.vb').read_text(encoding='utf-8')
    opener = codec.split('Private Function CSTP_OpenInput', 1)[1].split('End Function', 1)[0]
    assert 'For attempt = 1 To 3' in opener
    assert 'If attempt < 3 Then Wait 0.1' in opener
    assert 'operation=open; attempt=' in opener
    assert 'Err.Number' in opener and 'Err.Description' in opener
    assert 'Line Input' not in opener
    loader = codec.split('Private Function CSTP_LoadFields', 1)[1].split('End Function', 1)[0]
    assert 'CSTP_OpenInput' in loader
    assert 'operation=read; number=' in loader
    assert 'unexpected protocol header' in loader
    assert 'For attempt' not in loader


def test_shutdown_saves_before_stop_ack_and_has_independent_error_handler():
    macro = (ROOT / 'data/runtime_managed_worker_v1_main.vb').read_text(encoding='utf-8')
    close = macro.split('Private Sub CSTPMW_CloseSession', 1)[1].split('End Sub', 1)[0]
    assert close.index('\n    Save\n') < close.index('CSTP_WriteStopAck') < close.index('\n    Quit\n')
    assert 'On Error GoTo CloseFailed' in close
    assert 'For i = 1 To 10' not in close
    assert 'CSTP_ReadStopRequest' in close
    failure = close.split('CloseFailed:', 1)[1]
    assert 'CSTPMW_PublishFailure' not in failure
    assert '\n    Save\n' not in failure and '\n    Quit\n' not in failure
    assert 'number=' in failure


def test_ack_failure_preserves_completion_and_logs_each_cleanup_operation():
    macro = (ROOT / 'data/runtime_managed_worker_v1_main.vb').read_text(encoding='utf-8')
    assert 'stage = "ack-read"' in macro
    assert 'stage = "ack-cleanup"' in macro
    handler = macro.split('WorkerFailed:', 1)[1].split('End Sub', 1)[0]
    assert 'Resume AckWaitTick' in handler
    assert 'ackBlocked = True' in handler
    assert 'CSTP_WriteAckReceipt' in macro
    assert macro.index('CSTP_WriteAckReceipt') < macro.index('Kill "%TASK_PATH%"')
    assert 'Dir("%COMPLETION_PATH%") = ""' in handler
    assert 'delete-task' in macro and 'delete-completion' in macro and 'delete-ack' in macro
    assert '%LIFECYCLE_PATH%' in macro


def test_exited_worker_without_stop_ack_requires_reconciliation_not_kill(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker.ID = '0'
    from threading import RLock
    from csttool.runtime_protocol import FileProtocol
    worker._lock = RLock()
    worker.protocol = FileProtocol(worker.task_path.parent)
    # Process was alive on entry and exited while Python awaited Stop Ack.
    codes = iter([None, 0])
    worker._process = SimpleNamespace(pid=123, poll=lambda: next(codes, 0))
    monkeypatch.setattr(worker, '_close_log', lambda: None)
    monkeypatch.setattr(worker, '_diagnose_failure', lambda phase: None)
    with pytest.raises(ManagedWorkerShutdownError, match='process already exited') as captured:
        worker.stop()
    assert 'emergency termination' not in str(captured.value)
    assert worker.stop_request_path.exists()
