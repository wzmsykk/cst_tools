"""L1 evidence matrix: no CST, no process signalling, no result adoption."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

import pytest

from csttool.configuration import write_json_atomic
from csttool.project_session_recovery import discover_managed_sessions, recover_project_sessions
from csttool.runtime_protocol import FileProtocol, StopAcknowledge, encode_stop_ack, new_session_id
from csttool.session_closure import (CloseEvidence, evaluate_closure, read_stop_evidence,
                                    read_recorded_exit, write_close_verification)
from test.managed_cstworker_test import build_worker_shell


@pytest.mark.parametrize('alive', [True, None, False])
@pytest.mark.parametrize('code', [None, 0, 1, 4])
def test_exit_matrix_keeps_task_model_and_process_facts_separate(alive, code):
    evidence = CloseEvidence('session', alive, code, 'valid', True,
                             task_outcome='failure', result_state='acknowledged')
    result = evaluate_closure(evidence)
    assert result.standard_closed == (alive is False and code in (0, 4))
    assert result.needs_recovery != result.standard_closed
    assert result.task_outcome == 'failure'
    assert result.model_state == 'restored-saved'
    assert result.result_state == 'acknowledged'


@pytest.mark.parametrize('ack', ['missing', 'invalid'])
def test_exit_zero_does_not_replace_protocol_evidence(ack):
    assert evaluate_closure(CloseEvidence('session', False, 0, ack)).needs_recovery


def test_completion_and_abandonment_do_not_become_result_adoption():
    result = evaluate_closure(CloseEvidence('session', False, 1, 'valid', True,
        abandoned=True, unresolved_completion=True, task_outcome='failure'))
    assert result.disposition == 'abandoned-dead'
    assert result.needs_recovery
    assert not result.standard_closed
    assert result.exit_classification == 'abnormal'
    assert 'completion-not-reconciled' in result.missing_evidence


def session(tmp_path, *, ack='valid', code=None):
    sid = new_session_id()
    root = tmp_path / 'temp/worker_0' / sid
    protocol = FileProtocol(root / 'protocol')
    (root / 'worker.pid').write_text('99999999', encoding='ascii')
    (root / 'worker.state').write_text('stopped', encoding='ascii')
    if ack != 'missing':
        content = (encode_stop_ack(StopAcknowledge(sid if ack == 'valid' else new_session_id()))
                   if ack != 'corrupt' else 'bad header')
        (protocol.root / 'stop.ack').write_text(content, encoding='ascii')
    if code is not None:
        state = evaluate_closure(CloseEvidence(sid, False, code, ack))
        write_close_verification(root, 99999999, state)
    return sid, root, protocol


@pytest.mark.parametrize('alive', [True, None])
@pytest.mark.parametrize('disposition', [None, 'standard-stop', 'abandoned-dead'])
def test_stop_ack_and_receipt_never_hide_live_or_unknown_process(tmp_path, monkeypatch, alive, disposition):
    sid, root, _ = session(tmp_path, code=0)
    if disposition:
        write_json_atomic(root / 'recovery.json', dict(schema_version=1, worker_id='0',
            session_id=sid, disposition=disposition))
    monkeypatch.setattr('csttool.project_session_recovery._process_tree_is_alive', lambda pid: alive)
    assert discover_managed_sessions(tmp_path)[0].needs_recovery
    if alive is None:
        with pytest.raises(RuntimeError, match='unknown'):
            recover_project_sessions(tmp_path, timeout_per_session=.01)
        assert not (root / 'protocol/stop.request').exists()


@pytest.mark.parametrize('ack', ['wrong', 'corrupt'])
def test_malformed_or_wrong_session_stop_ack_preserves_evidence(tmp_path, ack):
    _, root, protocol = session(tmp_path, ack=ack, code=0)
    before = (protocol.root / 'stop.ack').read_bytes()
    assert discover_managed_sessions(tmp_path)[0].needs_recovery
    with pytest.raises(RuntimeError, match='invalid StopAck'):
        recover_project_sessions(tmp_path, timeout_per_session=.01)
    assert (protocol.root / 'stop.ack').read_bytes() == before
    assert not (root / 'recovery.json').exists()


def test_recorded_exit_is_scoped_and_proofs_are_verified(tmp_path):
    sid, root, protocol = session(tmp_path, code=0)
    assert read_recorded_exit(root, sid, 99999999) == 0
    assert read_recorded_exit(root, new_session_id(), 99999999) is None
    assert read_recorded_exit(root, sid, 7) is None
    (protocol.root / 'stop.ack').write_text('changed', encoding='ascii')
    assert read_recorded_exit(root, sid, 99999999) is None


def test_legacy_dead_ack_without_observed_exit_requires_explicit_abandonment(tmp_path):
    sid, root, _ = session(tmp_path)
    assert discover_managed_sessions(tmp_path)[0].needs_recovery
    recover_project_sessions(tmp_path, timeout_per_session=.1)
    value = json.loads((root / 'recovery.json').read_text())
    assert value['disposition'] == 'abandoned-dead'
    assert value['closure']['exit_code'] is None
    assert not value['closure']['standard_closed']
    assert not discover_managed_sessions(tmp_path)[0].needs_recovery


def test_legacy_unknown_process_is_not_closed_by_receipt(tmp_path):
    sid, root, _ = session(tmp_path, code=0)
    (root / 'worker.pid').unlink()
    assert discover_managed_sessions(tmp_path)[0].needs_recovery
    with pytest.raises(RuntimeError, match='unknown'):
        recover_project_sessions(tmp_path, timeout_per_session=.1)


def test_old_standard_receipt_is_preserved_when_reclassified(tmp_path):
    sid, root, _ = session(tmp_path)
    value = dict(schema_version=1, worker_id='0', session_id=sid, disposition='standard-stop')
    write_json_atomic(root / 'recovery.json', value)
    before = (root / 'recovery.json').read_bytes()
    recover_project_sessions(tmp_path, timeout_per_session=.1)
    assert (root / 'recovery.json').read_bytes() == before
    assert json.loads((root / 'recovery-l1.json').read_text())['disposition'] == 'abandoned-dead'
    assert not discover_managed_sessions(tmp_path)[0].needs_recovery


def test_discovery_cannot_skip_session_missing_worker_marker(tmp_path):
    _, root, _ = session(tmp_path, ack='missing')
    (root / 'worker.state').unlink()
    records = discover_managed_sessions(tmp_path)
    assert len(records) == 1 and records[0].needs_recovery
    assert records[0].marker == 'unknown'


@pytest.mark.parametrize('code', [0, 1, 4])
def test_worker_and_discovery_use_identical_closure_policy(tmp_path, monkeypatch, code):
    sid, root, protocol = session(tmp_path)
    worker = build_worker_shell(root)
    worker.ID, worker.session_id, worker.protocol = '0', sid, protocol
    worker._process = SimpleNamespace(pid=99999999, poll=lambda: code)
    worker._lock = RLock()
    worker.STOP_TIMEOUT = .01
    monkeypatch.setattr(worker, '_close_log', lambda: None)
    monkeypatch.setattr(worker, '_diagnose_failure', lambda phase: None)
    Path(str(worker.project_path) + '.recovery-saved').write_text(
        'CST_RECOVERY_SAVED_V1\n' + sid + '\n', encoding='ascii')
    Path(str(worker.project_path) + '.recovered.cst').write_bytes(b'isolated recovered model')
    expected = worker._shutdown_assessment()
    from csttool.managed_cstworker import ManagedWorkerShutdownError
    if code == 1:
        with pytest.raises(ManagedWorkerShutdownError):
            worker.stop()
    else:
        assert worker.stop()
    discovered = discover_managed_sessions(tmp_path)[0].closure
    assert asdict(discovered) == asdict(expected)
    assert discovered.standard_closed == (code in (0, 4))


def test_parent_exit_does_not_hide_live_or_unknown_descendant(monkeypatch):
    from csttool import project_session_recovery as recovery
    monkeypatch.setattr(recovery, '_windows_descendant_process_ids', lambda pid: {22})
    for child_state in (True, None, False):
        monkeypatch.setattr(recovery, '_process_is_alive', lambda pid: False if pid == 11 else child_state)
        assert recovery._process_tree_is_alive(11) is child_state
    monkeypatch.setattr(recovery, '_windows_descendant_process_ids', lambda pid: None)
    assert recovery._process_tree_is_alive(11) is None


def test_process_access_denied_is_unknown_not_dead(monkeypatch):
    import psutil
    from csttool.project_session_recovery import _process_is_alive
    def denied(pid):
        raise psutil.AccessDenied(pid)
    monkeypatch.setattr(psutil, 'Process', denied)
    assert _process_is_alive(123) is None


def test_exit_wait_checks_once_even_when_budget_is_exhausted(tmp_path, monkeypatch):
    from csttool import project_session_recovery as recovery
    _, _, _ = session(tmp_path)
    monkeypatch.setattr(recovery, '_process_tree_is_alive', lambda pid: False)
    record = discover_managed_sessions(tmp_path)[0]
    recovery._wait_for_process_exit(record, timeout=0)


def test_recovery_ack_and_exit_share_one_deadline(tmp_path, monkeypatch):
    from csttool import project_session_recovery as recovery
    sid, _, _ = session(tmp_path, code=0)
    closed = discover_managed_sessions(tmp_path)[0]
    active = replace(closed, process_alive=True)
    clock = [10.]
    probes = []
    def discover(project):
        return [active if not probes else closed]
    def stop(protocol, expected_session, *, timeout, peer_exited=None):
        assert expected_session == sid
        assert timeout == pytest.approx(1.)
        clock[0] += .7
        probes.append('ack')
    def wait(record, timeout):
        assert timeout == pytest.approx(.3)
        probes.append('exit')
    monkeypatch.setattr(recovery, 'discover_managed_sessions', discover)
    monkeypatch.setattr(recovery.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(recovery, 'recover_and_stop_session', stop)
    monkeypatch.setattr(recovery, '_wait_for_process_exit', wait)
    recovery.recover_project_sessions(tmp_path, timeout_per_session=1.)
    assert probes == ['ack', 'exit']
