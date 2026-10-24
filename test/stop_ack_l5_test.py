from types import SimpleNamespace
import pytest
from csttool.runtime_protocol import Task, Completion, CompletionStatus, encode_completion
from test.support.validate_stop_ack_l5 import read_current_completion, TimingWorker
from test.managed_cstworker_test import build_worker_shell


def test_timing_probe_reads_production_completion_and_checks_identity(tmp_path):
    task = Task.create('11111111-1111-4111-8111-111111111111', {})
    worker = SimpleNamespace(completion_path=tmp_path / 'current.completion')
    assert read_current_completion(worker, task) is None
    completion = Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS)
    worker.completion_path.write_text(encode_completion(completion))
    assert read_current_completion(worker, task) == completion
    other = Task.create(task.session_id, {})
    with pytest.raises(ValueError):
        read_current_completion(worker, other)


@pytest.mark.parametrize('phase', ['received', 'acknowledged'])
def test_completed_ack_cleanup_still_requires_result_reconciliation(tmp_path, monkeypatch, phase):
    from test.project_session_recovery_test import _session
    from csttool.configuration import write_json_atomic
    import csttool.project_session_recovery as recovery
    from csttool.runtime_protocol import new_session_id, StopAcknowledge, encode_stop_ack
    sid, root, protocol = _session(tmp_path, 'stopped')
    task_id = new_session_id()
    (root / 'worker.pid').write_text('123')
    (protocol.root / 'stop.ack').write_text(encode_stop_ack(StopAcknowledge(sid)))
    monkeypatch.setattr(recovery, '_process_tree_is_alive', lambda _: False)
    monkeypatch.setattr(recovery, 'read_recorded_exit', lambda *args: 0)
    receipt_path = root / 'received' / (task_id + '.json')
    write_json_atomic(root / 'task-context.json', dict(task_id=task_id, session_id=sid, receipt_path=str(receipt_path)))
    snapshot = root / 'result.cst'
    snapshot.write_bytes(b'synthetic confirmed result, not a real CST model')
    from csttool.result_reconciliation import file_hash
    receipt = dict(task_id=task_id, session_id=sid, status='Success', phase=phase,
                   snapshot=str(snapshot), snapshot_sha256=file_hash(snapshot))
    write_json_atomic(receipt_path, receipt)
    record = recovery.discover_managed_sessions(tmp_path)[0]
    assert record.closure.standard_closed and record.needs_recovery
    assert 'received-result-not-reconciled' in record.closure.missing_evidence
    assert 'completion-not-reconciled' not in record.closure.missing_evidence
    recovery.recover_project_sessions(tmp_path)
    assert not recovery.discover_managed_sessions(tmp_path)[0].needs_recovery
    import json
    assert json.loads((root / 'recovery.json').read_text())['received_task_id'] == task_id
    # A different task cannot borrow that reconciliation decision.
    other = new_session_id()
    write_json_atomic(root / 'task-context.json', dict(task_id=other, session_id=sid, receipt_path=str(receipt_path)))
    write_json_atomic(receipt_path, dict(receipt, task_id=other))
    assert recovery.discover_managed_sessions(tmp_path)[0].needs_recovery


@pytest.mark.parametrize('point', ['before-parameters', 'after-rebuild', 'after-solver',
                                  'completion-before-receive', 'ack-accepted', 'task-deleted', 'completion-deleted'])
def test_real_timing_macro_keeps_protocol_and_adds_only_owned_gate(tmp_path, point):
    shell = build_worker_shell(tmp_path)
    worker = TimingWorker.__new__(TimingWorker)
    worker.__dict__.update(shell.__dict__)
    worker.batch_script_path = worker.project_path.with_suffix('') / 'Model/3D/Model.run'
    worker.point = point
    worker._build_macro()
    source = worker.macro_path.read_text()
    assert source.count('timing.entered') == 1
    assert str(worker.root / 'timing.release') in source
    assert '            solverReturn = EigenmodeSolver.Start' in source
    assert '                    Kill ' in source
    assert 'CSTPMW_CloseSession' in source
