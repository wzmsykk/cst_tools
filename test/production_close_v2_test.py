"""Real Python worker lifecycle with an explicitly synthetic VBA peer.

The peer implements protocol transitions, not electromagnetic/CST semantics.
Source contracts below inspect the actual macro; they do not execute WinWrap.
"""
import json
from pathlib import Path
from threading import Event, RLock, Thread
import time
import traceback
from types import SimpleNamespace

import pytest

from csttool.close_receipt import CloseReceipt, declare_close_protocol, publish_close_receipt, read_close_receipt
from csttool.configuration import write_json_atomic
from csttool.managed_cstworker import ManagedWorkerShutdownError
from csttool.runtime_protocol import (Acknowledge, Completion, CompletionStatus, ErrorCode,
    FileProtocol, StopAcknowledge, atomic_publish, decode_task, decode_ack,
    encode_ack, encode_completion, encode_stop_ack)
from csttool.session_closure import collect_close_evidence, evaluate_closure
from csttool.project_session_recovery import recover_project_sessions, discover_managed_sessions
from test.managed_cstworker_test import build_worker_shell


MACRO = Path('data/runtime_managed_worker_v1_main.vb')


class MacroPeer:
    """No CST launch: deterministic failure, ACK cleanup, close and exit."""
    def __init__(self, worker, outcome, close_fault=None, exit_code=0):
        self.worker, self.outcome, self.close_fault = worker, outcome, close_fault
        self.exit_code = exit_code
        self.exited, self.cancel = Event(), Event()
        self.tasks, self.operations = [], []
        self.error = None
        self.error_traceback = ''
        self.thread = Thread(target=self.run, daemon=True)

    def run(self):
        worker = self.worker
        try:
            task = None
            retired = False
            while not self.cancel.is_set():
                if worker.stop_request_path.exists():
                    if task is None:
                        task_id, task_outcome = 'none', 'not-started'
                    else:
                        task_id = task.task_id
                        task_outcome = 'success' if self.outcome == 'success' else 'failure'
                    model, close, ref = 'committed', 'saved', 'worker-input.cst'
                    if self.outcome == 'solver-failure' and task is not None:
                        self.operations.append('restore')
                        if self.close_fault != 'restore':
                            self.operations.append('rebuild')
                        if self.close_fault not in {'restore', 'rebuild'}:
                            self.operations.append('backup')
                        model, close, ref = 'restored-saved', 'restored-saved', 'worker-input.cst.recovered.cst'
                        if self.close_fault not in {'restore', 'rebuild', 'backup'}:
                            (worker.root / ref).write_bytes(b'restored')
                        if self.close_fault in {None, 'receipt'}:
                            Path(str(worker.project_path) + '.recovery-saved').write_text(
                                'CST_RECOVERY_SAVED_V1\n' + worker.session_id + '\n', encoding='ascii')
                    if task is None:
                        model = 'prepared'
                    if self.close_fault not in {'restore', 'rebuild', 'backup'}:
                        self.operations.append('save')
                    failures = {
                        'restore': ('restore-failed', 'none', 'CLOSE_RESTORE_FAILED'),
                        'rebuild': ('restore-failed', 'restore', 'CLOSE_REBUILD_FAILED'),
                        'backup': ('unknown', 'rebuild', 'CLOSE_BACKUP_FAILED'),
                        'save': ('unknown', 'backup', 'CLOSE_SAVE_FAILED'),
                        'recovery-receipt': ('unknown', 'save', 'CLOSE_RECEIPT_FAILED'),
                    }
                    if self.close_fault in failures:
                        failed_model, last_phase, error_code = failures[self.close_fault]
                        frame = CloseReceipt(worker.session_id, task_id, 'stop-request', task_outcome,
                            'failed', failed_model, last_phase, 'none', 0, error_code)
                    else:
                        frame = CloseReceipt(worker.session_id, task_id, 'stop-request', task_outcome,
                            close, model, 'save', ref, (worker.root / ref).stat().st_size, 'none')
                    if self.close_fault == 'receipt':
                        (worker.root / 'protocol/close.receipt.tmp').write_bytes(b'blocked publication')
                    try:
                        publish_close_receipt(worker.root, frame)
                    except Exception:
                        if self.close_fault != 'receipt':
                            raise
                    if not self.close_fault:
                        self.operations.append('close-receipt')
                        atomic_publish(worker.stop_ack_path, encode_stop_ack(StopAcknowledge(worker.session_id)))
                        self.operations.append('stop-ack')
                    self.exited.set()
                    return
                if not retired and worker.task_path.exists() and task is None:
                    task = decode_task(worker.task_path.read_text(encoding='ascii'))
                    self.tasks.append(task.task_id)
                    self.operations.append('solver')
                    folder = worker.result_root / task.task_id
                    folder.mkdir(parents=True)
                    if self.outcome == 'success':
                        (folder / 'project.cst').write_bytes(b'accepted task snapshot')
                        (folder / 'project').mkdir()
                    completion = Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS) if self.outcome == 'success' else Completion(
                        task.task_id, task.session_id, CompletionStatus.FAILURE,
                        ErrorCode.SOLVER_FAILED if self.outcome == 'solver-failure' else ErrorCode.RESULT_FLUSH_FAILED,
                        'synthetic failure')
                    atomic_publish(worker.completion_path, encode_completion(completion))
                if task is not None and worker.ack_path.exists():
                    assert decode_ack(worker.ack_path.read_text()) == Acknowledge(task.task_id, task.session_id)
                    atomic_publish(str(worker.ack_path) + '.' + task.task_id + '.accepted',
                                   encode_ack(Acknowledge(task.task_id, task.session_id)))
                    for path in (worker.task_path, worker.completion_path, worker.ack_path):
                        path.unlink()
                    retired = self.outcome != 'success'
                    worker.marker_path.write_text(('retiring:' if retired else 'ready:') + task.task_id, encoding='ascii')
                time.sleep(.005)
        except Exception as exc:
            self.error = exc
            self.error_traceback = traceback.format_exc()
            self.exited.set()


@pytest.fixture
def peer_factory(tmp_path, monkeypatch):
    peers = []
    def create(outcome='success', close_fault=None, exit_code=0):
        project = tmp_path / str(len(peers))
        root = project / 'temp/worker_0/11111111-1111-4111-8111-111111111111'
        root.mkdir(parents=True)
        worker = build_worker_shell(root)
        worker.ID, worker._lock, worker._stopping = '0', RLock(), False
        worker._retiring, worker.close_protocol, worker.START_TIMEOUT, worker.STOP_TIMEOUT = False, 'v2', 2., 2.
        worker._run_in_background = False  # Synthetic peer has no native window.
        worker.parameter_definitions, worker.postprocess_settings = (), []
        worker.execution_fingerprint = None
        from csttool.cst_memory_guard import MemoryGuardPolicy
        worker._memory_guard_policy = MemoryGuardPolicy(enabled=False)
        worker.protocol = FileProtocol(worker.task_path.parent)
        declare_close_protocol(root, worker.session_id, 'v2')
        worker.project_path.write_bytes(b'working!')
        field = root / 'worker-input/Result/e-field.bin'
        field.parent.mkdir(parents=True)
        field.write_bytes(b'only solved field; preserve')
        (root / 'worker.pid').write_text('99999999', encoding='ascii')
        worker.marker_path.write_text('ready', encoding='ascii')
        peer = MacroPeer(worker, outcome, close_fault, exit_code)
        worker._process = SimpleNamespace(pid=99999999, poll=lambda: exit_code if peer.exited.is_set() else None)
        monkeypatch.setattr(worker, '_wait_for_marker', lambda *args: None)
        monkeypatch.setattr(worker, '_close_log', lambda: None)
        monkeypatch.setattr(worker, '_diagnose_failure', lambda phase: None)
        monkeypatch.setattr(worker.postprocess, 'read_all_results', lambda: [])
        monkeypatch.setattr('csttool.project_session_recovery._process_tree_is_alive', lambda pid: not peer.exited.is_set())
        peer.thread.start()
        peers.append(peer)
        return project, worker, peer, field
    yield create
    for peer in peers:
        peer.cancel.set()
        peer.thread.join(3)
        assert not peer.thread.is_alive()
        assert peer.error is None, peer.error_traceback


@pytest.mark.parametrize('outcome', ['success', 'solver-failure', 'postprocess-failure'])
def test_actual_python_ack_and_close_with_synthetic_peer(peer_factory, outcome):
    _, worker, peer, field = peer_factory(outcome)
    before = field.read_bytes()
    result = worker.run_task('task', params={})
    assert result.status == ('Success' if outcome == 'success' else 'Failure')
    if outcome != 'success':
        assert result.snapshot is None  # Saved close state never promotes a failed task.
    assert worker.retiring == (outcome != 'success')
    if worker.retiring:
        with pytest.raises(RuntimeError, match='retiring'):
            worker.run_task('must-not-run', params={})
        assert not worker.task_path.exists()
    assert worker.stop()
    peer.thread.join(2)
    frame = read_close_receipt(worker.root, worker.session_id, expected_task_id=result.task_id)
    assert frame.task_outcome == ('success' if outcome == 'success' else 'failure')
    assert frame.close_outcome == ('restored-saved' if outcome == 'solver-failure' else 'saved')
    assert peer.operations.count('solver') == 1
    assert ('rebuild' in peer.operations) == (outcome == 'solver-failure')
    assert peer.operations.index('close-receipt') < peer.operations.index('stop-ack')
    assert field.read_bytes() == before
    assert worker._shutdown_assessment().task_outcome == frame.task_outcome


def test_repeated_stop_after_solver_failure_ack_does_not_publish_conflict(peer_factory):
    _, worker, peer, field = peer_factory('solver-failure')
    before = field.read_bytes()
    result = worker.run_task('failed-once', params={})
    assert result.status == 'Failure' and worker.retiring
    worker.request_stop()  # Manager replacement path.
    content = worker.stop_request_path.read_bytes()
    worker.request_stop()  # Manager stop broadcast after replacement failure.
    assert worker.stop_request_path.read_bytes() == content
    assert worker.stop()
    assert peer.operations.count('solver') == 1
    assert field.read_bytes() == before


def test_solver_failure_diagnostic_keeps_actual_non_success_return():
    source = Path('data/runtime_managed_worker_v1_main.vb').read_text(encoding='utf-8')
    failed = source.split('If solverReturn <> 1 Then', 1)[1].split('End If', 1)[0]
    assert '"EigenmodeSolver.Start returned " & CStr(solverReturn)' in failed
    assert '"EigenmodeSolver.Start returned 0"' not in failed


@pytest.mark.parametrize('fault', ['restore', 'rebuild', 'backup', 'save', 'recovery-receipt', 'receipt'])
def test_close_failure_preserves_evidence_and_blocks_positive_ack(peer_factory, fault):
    project, worker, peer, field = peer_factory('solver-failure', fault, exit_code=4)
    baseline = project / 'last-confirmed.cst'
    baseline.write_bytes(b'last confirmed model; never replace with failure')
    worker.run_task('failure', params={})
    before = field.read_bytes()
    with pytest.raises(ManagedWorkerShutdownError):
        worker.stop()
    assert not worker.stop_ack_path.exists()
    assert discover_managed_sessions(project)[0].needs_recovery
    if fault != 'receipt':
        assert read_close_receipt(worker.root, worker.session_id).close_outcome == 'failed'
        recover_project_sessions(project, timeout_per_session=.1)
        assert not discover_managed_sessions(project)[0].needs_recovery
    else:
        with pytest.raises(RuntimeError, match='close protocol'):
            recover_project_sessions(project, timeout_per_session=.1)
        assert (worker.root / 'protocol/close.receipt.tmp').read_bytes() == b'blocked publication'
    assert field.read_bytes() == before
    assert baseline.read_bytes() == b'last confirmed model; never replace with failure'


def test_task_scoped_ack_does_not_accept_old_ready_or_incomplete_cleanup(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker.close_protocol, worker.START_TIMEOUT = 'v2', .02
    from csttool.runtime_protocol import Task
    task = Task.create(worker.session_id, {})
    monkeypatch.setattr(worker, '_ensure_running', lambda: None)
    worker.marker_path.write_text('ready', encoding='ascii')
    with pytest.raises(TimeoutError):
        worker._wait_task_ack(task)
    worker.marker_path.write_text('ready:' + task.task_id, encoding='ascii')
    with pytest.raises(RuntimeError, match='accepted receipt'):
        worker._wait_task_ack(task)
    atomic_publish(str(worker.ack_path) + '.' + task.task_id + '.accepted', encode_ack(Acknowledge(task.task_id, task.session_id)))
    worker.task_path.write_text('not cleaned', encoding='ascii')
    with pytest.raises(TimeoutError):
        worker._wait_task_ack(task)
    worker.task_path.unlink()
    assert worker._wait_task_ack(task) == 'ready'


def test_macro_actual_stage_and_protection_contracts():
    source = MACRO.read_text(encoding='ascii')
    close = source.split('Private Sub CSTPMW_CloseSession', 1)[1].split('End Sub', 1)[0]
    assert close.index('If activeTaskSolveReady Or solverReturnedSuccess Then') < close.index('If modelNeedsRecovery Then')
    assert close.index('\n    Save\n') < close.index('CSTC2_WriteCloseReceipt') < close.index('CSTP_WriteStopAck')
    assert 'workerRetiring = True' in source.split('Private Sub CSTPMW_PublishFailure', 1)[1]
    assert source.index('If workerRetiring Then') < source.index('ElseIf Dir("%TASK_PATH%")')
    assert '"retiring:" & task.TaskId' in source and '"ready:" & task.TaskId' in source
    publish = source.split('Private Sub CSTPMW_PublishFailure', 1)[1].split('End Sub', 1)[0]
    assert 'If activeTaskSolveReady Or solverReturnedSuccess Then' in publish and 'modelNeedsRecovery = False' in publish
    assert 'Rebuild' not in publish
    failure = close.split('CloseFailed:', 1)[1]
    for code in ('CLOSE_RESTORE_FAILED', 'CLOSE_REBUILD_FAILED', 'CLOSE_BACKUP_FAILED',
                 'CLOSE_SAVE_FAILED', 'CLOSE_RECEIPT_FAILED', 'CLOSE_PROTOCOL_ERROR'):
        assert code in failure
    assert 'CSTC2_WriteCloseReceipt' in failure
    assert 'CSTP_WriteStopAck' not in failure and '\n    Save\n' not in failure and 'Rebuild' not in failure


@pytest.mark.parametrize('exit_code', [0, 1])
def test_autonomous_v2_close_needs_no_forged_stop_ack(tmp_path, exit_code):
    from csttool.runtime_protocol import new_session_id
    sid = new_session_id()
    declare_close_protocol(tmp_path, sid, 'v2')
    (tmp_path / 'worker-input.cst').write_bytes(b'saved')
    frame = CloseReceipt(sid, 'none', 'worker-failure', 'unknown', 'saved', 'prepared',
                         'save', 'worker-input.cst', 5, 'none')
    publish_close_receipt(tmp_path, frame)
    facts = collect_close_evidence(tmp_path, sid, False, exit_code, expected_close_protocol='v2')
    assert facts.stop_ack == 'missing' and not facts.stop_ack_required
    assert evaluate_closure(facts).standard_closed == (exit_code == 0)


def test_generator_now_declares_v2_and_combines_both_codecs(tmp_path):
    worker = build_worker_shell(tmp_path)
    worker._build_macro()
    macro = worker.macro_path.read_text(encoding='ascii')
    assert worker.close_protocol == 'v2'
    assert json.loads((tmp_path / 'close-protocol.json').read_text())['close_protocol'] == 'v2'
    assert 'Public Function CSTC2_WriteCloseReceipt' in macro
    assert '%CLOSE_RECEIPT_PATH%' not in macro
    assert str(tmp_path / 'protocol/close.receipt') in macro
    assert macro.lower().count('sub main') == 1


def test_stop_before_pending_dispatch_is_not_a_fake_task_success(tmp_path):
    from csttool.runtime_protocol import new_session_id
    sid, pending = new_session_id(), new_session_id()
    declare_close_protocol(tmp_path, sid, 'v2')
    FileProtocol(tmp_path / 'protocol').request_stop(sid)
    write_json_atomic(tmp_path / 'task-context.json', dict(session_id=sid, task_id=pending, close_protocol='v2'))
    (tmp_path / 'worker-input.cst').write_bytes(b'untouched')
    frame = CloseReceipt(sid, 'none', 'stop-request', 'not-started', 'saved', 'prepared',
                         'save', 'worker-input.cst', 9, 'none')
    publish_close_receipt(tmp_path, frame)
    atomic_publish(tmp_path / 'protocol/stop.ack', encode_stop_ack(StopAcknowledge(sid)))
    facts = collect_close_evidence(tmp_path, sid, False, 0, expected_close_protocol='v2')
    assert facts.protocol_error is None and facts.task_outcome == 'not-started'
    assert evaluate_closure(facts).standard_closed
    assert not (tmp_path / 'protocol/current.completion').exists()


def test_previous_task_receipt_requires_proof_and_cannot_hide_later_ack(tmp_path):
    from csttool.runtime_protocol import new_session_id
    sid, previous, pending = new_session_id(), new_session_id(), new_session_id()
    declare_close_protocol(tmp_path, sid, 'v2')
    FileProtocol(tmp_path / 'protocol').request_stop(sid)
    write_json_atomic(tmp_path / 'task-context.json', dict(session_id=sid, task_id=pending, close_protocol='v2'))
    (tmp_path / 'worker-input.cst').write_bytes(b'last saved')
    frame = CloseReceipt(sid, previous, 'stop-request', 'success', 'saved', 'committed',
                         'save', 'worker-input.cst', 10, 'none')
    publish_close_receipt(tmp_path, frame)
    assert collect_close_evidence(tmp_path, sid, False, 0).protocol_error
    atomic_publish(tmp_path / ('protocol/current.ack.' + previous + '.accepted'), encode_ack(Acknowledge(previous, sid)))
    assert collect_close_evidence(tmp_path, sid, False, 0).protocol_error is None
    atomic_publish(tmp_path / ('protocol/current.ack.' + pending + '.accepted'), encode_ack(Acknowledge(pending, sid)))
    assert collect_close_evidence(tmp_path, sid, False, 0).protocol_error
