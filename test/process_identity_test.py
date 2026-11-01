import json
from pathlib import Path

import pytest
from csttool import process_identity as identity
from csttool import project_session_recovery as recovery


class Process:
    def create_time(self): return 10.0
    def exe(self): return str(Path('cst.exe').resolve())


def record(tmp_path, monkeypatch):
    monkeypatch.setattr(identity.psutil, 'Process', lambda pid: Process())
    identity.capture_process_identity(tmp_path, 42, Process().exe(), tmp_path/'worker-input.cst')


def test_identity_match_and_pid_reuse(tmp_path, monkeypatch):
    record(tmp_path, monkeypatch)
    assert identity.observe_process_identity(tmp_path, 42)[0] == 'matched'
    monkeypatch.setattr(Process, 'create_time', lambda self: 11.0)
    assert identity.observe_process_identity(tmp_path, 42)[0] == 'reused'
    monkeypatch.setattr(recovery, 'read_recorded_exit', lambda *a: None)
    monkeypatch.setattr(recovery, '_process_tree_is_alive', lambda *a: pytest.fail('must not observe unrelated PID tree'))
    assert recovery._owned_alive(tmp_path, 42)[0] is None


def test_legacy_live_pid_unknown_but_verified_exit_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, '_process_tree_is_alive', lambda pid: True)
    monkeypatch.setattr(recovery, 'read_recorded_exit', lambda *a: None)
    assert recovery._owned_alive(tmp_path, 42)[0] is None
    monkeypatch.setattr(recovery, 'read_recorded_exit', lambda *a: 0)
    assert recovery._owned_alive(tmp_path, 42)[0] is False


def test_invalid_and_denied_identity(tmp_path, monkeypatch):
    record(tmp_path, monkeypatch)
    monkeypatch.setattr(identity.psutil, 'Process', lambda pid: (_ for _ in ()).throw(identity.psutil.AccessDenied(pid)))
    assert identity.observe_process_identity(tmp_path,42)[0] == 'unknown'
    p=tmp_path/'process-identity.json';v=json.loads(p.read_text());v['project']=str(tmp_path/'wrong.cst');p.write_text(json.dumps(v))
    assert identity.observe_process_identity(tmp_path,42)[0] == 'unknown'


def test_reused_pid_never_enters_protocol_wait(tmp_path, monkeypatch):
    session = tmp_path/'temp/worker_0/session'
    (session/'protocol').mkdir(parents=True)
    (session/'worker.pid').write_text('42')
    (session/'worker.state').write_text('running')
    monkeypatch.setattr(recovery,'observe_process_identity',lambda *a:('reused','PID reused'))
    monkeypatch.setattr(recovery,'read_recorded_exit',lambda *a:None)
    monkeypatch.setattr(recovery,'recover_and_stop_session',lambda *a,**k:pytest.fail('must not wait'))
    events=[]
    with pytest.raises(RuntimeError,match='PID reused'):
        recovery.recover_project_sessions(tmp_path,progress=events.append)
    assert any(e.get('session_id')=='session' for e in events)
    assert not (session/'protocol/stop.request').exists()


def test_missing_parent_never_attributes_unverified_orphan(tmp_path, monkeypatch):
    record(tmp_path,monkeypatch)
    monkeypatch.setattr(identity.psutil,'Process',lambda pid: (_ for _ in ()).throw(identity.psutil.NoSuchProcess(pid)))
    monkeypatch.setattr(recovery,'read_recorded_exit',lambda *a:None)
    monkeypatch.setattr(recovery,'_windows_descendant_process_ids',lambda pid:{50})
    assert recovery._owned_alive(tmp_path,42)[0] is None
    monkeypatch.setattr(recovery,'_windows_descendant_process_ids',lambda pid:set())
    assert recovery._owned_alive(tmp_path,42)[0] is False
