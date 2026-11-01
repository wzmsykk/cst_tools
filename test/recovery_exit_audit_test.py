"""Offline fault acceptance for audit A01-A08; no CST launch."""
from pathlib import Path
from threading import Event, Thread
import json
import pytest
from csttool.runner import Runner
from csttool.runner_client import RunnerClient, RunnerRejected
from csttool.recovery_control import RecoveryPaused
from csttool.configuration import write_json_atomic, read_json
from csttool.runtime_protocol import FileProtocol,Completion,CompletionStatus,new_session_id,encode_completion
from csttool.managed_session_recovery import recover_and_stop_session
from csttool import project_session_recovery as sessions
from csttool.diagnostic_bundle import export_failure_bundle,ExportCancelled
from test.runner_test import WaitingExecution,command


def historical_intents(project):
    for index,run in enumerate(('run-a','run-b')):
        write_json_atomic(project/f'control/commands/old-{index}.json',
            dict(command=command('start'),result=dict(run_id=run)))


def test_all_historical_intents_close_once_and_stay_closed_on_restart(tmp_path):
    historical_intents(tmp_path)
    r=Runner(tmp_path,WaitingExecution)
    try:
        r.command(command('claim'))
        operation=r.command(command('recover'))['run_id']
        assert operation not in ('run-a','run-b')
        r.worker.join(5);assert not r.worker.is_alive()
        assert r.status['state']=='IDLE'
        before={run:(tmp_path/f'control/runs/{run}/outcome.json').read_bytes() for run in ('run-a','run-b')}
        assert all(json.loads(v)['state']=='INTERRUPTED' for v in before.values())
        r.command(command('recover'));r.worker.join(5)
        assert before=={run:(tmp_path/f'control/runs/{run}/outcome.json').read_bytes() for run in before}
    finally:r.close()
    r=Runner(tmp_path,WaitingExecution)
    try:assert r.status['state']=='IDLE'
    finally:r.close()


def test_stop_intent_for_unfinished_start_is_durable_without_faking_outcome(tmp_path):
    historical_intents(tmp_path);r=Runner(tmp_path,WaitingExecution)
    try:
        r.command(command('claim'))
        result=r.command(command('cancel_start',{'start_request_id':'old-0'}))
        assert result['accepted'] and r.status['state']=='RECOVERY_REQUIRED'
        assert not (tmp_path/'control/runs/run-a/outcome.json').exists()
        assert (tmp_path/'control/cancelled-starts/old-0.json').exists()
    finally:r.close()


def test_shutdown_hash_does_not_block_status_and_revalidates_control(tmp_path,monkeypatch):
    entered,release=Event(),Event();errors=[];r=Runner(tmp_path,WaitingExecution)
    def slow(project):entered.set();assert release.wait(4)
    monkeypatch.setattr('csttool.runner.verify_shutdown_safety',slow)
    def shutdown():
        try:r.command(command('shutdown'))
        except Exception as e:errors.append(str(e))
    try:
        r.command(command('claim'));thread=Thread(target=shutdown);thread.start();assert entered.wait(2)
        assert r.snapshot()['state']=='IDLE'
        with r.lock:r.owner_seen-=11
        r.command(command('claim',client_id='other'))
        release.set();thread.join(3);assert not thread.is_alive()
        assert errors and 'changed' in errors[0]
        assert not r.shutdown_requested.is_set()
    finally:release.set();r.close()


def test_discovery_reads_exit_proof_once_per_session(tmp_path,monkeypatch):
    sid=new_session_id();root=tmp_path/'temp/worker_0'/sid
    FileProtocol(root/'protocol');(root/'worker.pid').write_text('42')
    calls=[]
    monkeypatch.setattr(sessions,'read_recorded_exit',lambda *a:(calls.append(a) or 0))
    monkeypatch.setattr(sessions,'observe_process_identity',lambda *a:('reused','other process'))
    assert sessions.discover_managed_sessions(tmp_path)[0].process_alive is False
    assert len(calls)==1


def test_recovery_only_rescans_one_session_not_whole_project(tmp_path,monkeypatch):
    for _ in range(3):
        root=tmp_path/'temp/worker_0'/new_session_id();FileProtocol(root/'protocol');(root/'worker.pid').write_text('42')
    monkeypatch.setattr(sessions,'_process_tree_is_alive',lambda pid:False)
    count=[];original=sessions.discover_managed_sessions
    def discover(*a,**kw):count.append(1);return original(*a,**kw)
    monkeypatch.setattr(sessions,'discover_managed_sessions',discover)
    sessions.recover_project_sessions(tmp_path)
    assert len(count)==2


def test_pause_after_ack_preserves_frames_and_can_resume(tmp_path):
    sid,tid=new_session_id(),new_session_id();p=FileProtocol(tmp_path/'protocol')
    (p.root/'current.completion').write_text(encode_completion(Completion(tid,sid,CompletionStatus.SUCCESS)),encoding='ascii')
    pause=Event()
    def check():
        if pause.is_set():raise RecoveryPaused('pause')
    def peer():pause.set();return False
    with pytest.raises(RecoveryPaused):
        recover_and_stop_session(p.root,sid,pause_check=check,peer_exited=peer,poll_interval=0)
    before=(p.root/'current.ack').read_bytes()
    assert (p.root/'current.completion').exists()
    assert recover_and_stop_session(p.root,sid,peer_exited=lambda:True).task_id==tid
    assert (p.root/'current.ack').read_bytes()==before


def test_offline_runner_checks_lock_and_physical_safety_without_restart(tmp_path,monkeypatch):
    client=RunnerClient(tmp_path)
    monkeypatch.setattr(client,'connect',lambda **kw:(_ for _ in ()).throw(OSError('offline')))
    assert client.shutdown_and_wait()['already_offline']
    assert not client.launch_attempted
    monkeypatch.setattr('csttool.runner.verify_shutdown_safety',lambda p:(_ for _ in ()).throw(ValueError('unknown CST')))
    with pytest.raises(ValueError,match='unknown CST'):client.shutdown_and_wait()


def test_export_cancel_removes_partial_output_and_keeps_sources(tmp_path):
    source=tmp_path/'control/status.json';write_json_atomic(source,dict(state='FAILED'))
    before=source.read_bytes();cancel=Event()
    with pytest.raises(ExportCancelled):
        export_failure_bundle(tmp_path,cancel_check=cancel.is_set,progress=lambda e:cancel.set())
    assert source.read_bytes()==before
    assert not list((tmp_path/'diagnostics').glob('*.zip'))
    assert not list((tmp_path/'diagnostics').glob('.export-*.tmp'))


def test_paused_adoption_resumes_without_duplicate_results(tmp_path):
    from test.checkpoint_adoption_test import fixture,adoptions
    from csttool.checkpoint_adoption import reconcile_checkpoint_adoptions
    task,store,receipt,snapshot,checkpoint=fixture(tmp_path)
    before=snapshot.read_bytes(),checkpoint.read_bytes();calls=[]
    def pause():
        calls.append(1)
        if len(calls)==2:raise RecoveryPaused('paused before adoption')
    with pytest.raises(RecoveryPaused):reconcile_checkpoint_adoptions(tmp_path,pause_check=pause)
    assert read_json(receipt)['phase']=='acknowledged'
    reconcile_checkpoint_adoptions(tmp_path);reconcile_checkpoint_adoptions(tmp_path)
    assert len(adoptions(store,task))==1
    assert before==(snapshot.read_bytes(),checkpoint.read_bytes())


def test_corrupt_historical_intent_blocks_reconciliation_without_erasing_evidence(tmp_path):
    bad=tmp_path/'control/commands/broken.json';bad.parent.mkdir(parents=True);bad.write_text('{')
    r=Runner(tmp_path,WaitingExecution)
    try:
        assert r.status['intent_diagnostics']
        r.command(command('claim'));r.command(command('recover'));r.worker.join(5)
        assert r.status['state']=='RECOVERY_REQUIRED'
        assert bad.read_text()=='{'
    finally:r.close()


def test_pause_recovery_preserves_unfinished_start_intents(tmp_path):
    historical_intents(tmp_path)
    entered,release=Event(),Event()
    class Recovery(WaitingExecution):
        def recover(self):
            entered.set();assert release.wait(3)
            if self.stop.is_set():raise RecoveryPaused('user paused recovery')
    r=Runner(tmp_path,Recovery)
    try:
        r.command(command('claim'));r.command(command('recover'));assert entered.wait(2)
        r.command(command('stop',run_id=r.status['run_id']));release.set();r.worker.join(4)
        assert r.status['state']=='RECOVERY_REQUIRED'
        assert r.status['recovery_progress']['stage']=='paused'
        assert not (tmp_path/'control/runs/run-a/outcome.json').exists()
    finally:release.set();r.close()


def test_partial_intent_backfill_is_resumable_and_does_not_overwrite_first_proof(tmp_path,monkeypatch):
    import csttool.runner as module
    historical_intents(tmp_path);r=Runner(tmp_path,WaitingExecution);original=module.write_json_atomic
    def disk_error(path,data):
        if Path(path).name=='outcome.json' and Path(path).parent.name=='run-b':raise OSError('injected disk full')
        return original(path,data)
    try:
        r.command(command('claim'))
        with monkeypatch.context() as m:
            m.setattr(module,'write_json_atomic',disk_error)
            r.command(command('recover'));r.worker.join(5)
        assert r.status['state']=='RECOVERY_REQUIRED'
        first=(tmp_path/'control/runs/run-a/outcome.json').read_bytes()
        r.command(command('recover'));r.worker.join(5)
        assert r.status['state']=='IDLE'
        assert first==(tmp_path/'control/runs/run-a/outcome.json').read_bytes()
        assert read_json(tmp_path/'control/runs/run-b/outcome.json')['state']=='INTERRUPTED'
    finally:r.close()


def test_solver_wait_requires_current_task_and_explicit_trace(tmp_path):
    from csttool.runtime_protocol import Task,encode_task
    root=tmp_path/'temp/worker_0'/new_session_id();p=FileProtocol(root/'protocol')
    task=Task.create(root.name,{'fmin':1});(p.root/'current.task').write_text(encode_task(task),encoding='ascii')
    write_json_atomic(root/'task-context.json',dict(session_id=root.name,task_id=task.task_id))
    trace=root/'lifecycle.log'
    trace.write_text(f'now | stage=solver-start; path={root / "worker-input.cst"}; calling EigenmodeSolver.Start\n',encoding='utf-8')
    assert sessions._solver_call_active(root,tmp_path)
    trace.write_text(f'now | stage=solver-start; path={root / "worker-input.cst"}; returned=0\n',encoding='utf-8')
    assert not sessions._solver_call_active(root,tmp_path)


def test_pause_before_recovery_keeps_project_lock_released(tmp_path):
    from test.application_backend_test import make_backend
    from csttool.application_backend import BackendState
    from csttool.project_run_lock import ProjectRunLock
    backend,_,project,*_=make_backend();project.currProjectDir=tmp_path
    backend.stop_intent.request()
    with pytest.raises(RecoveryPaused):backend.recover_project_sessions()
    assert backend.state is BackendState.RECOVERY_REQUIRED
    assert ProjectRunLock.active_owner(tmp_path) is None


def test_cli_shutdown_of_offline_project_confirms_without_starting_service(tmp_path):
    import subprocess,sys
    result=subprocess.run([sys.executable,'-m','csttool.runner_client','--project',str(tmp_path),'shutdown'],
        cwd=Path(__file__).parents[1],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['already_offline']
    assert not (tmp_path/'control/runner.json').exists()
