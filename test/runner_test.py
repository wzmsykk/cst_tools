"""Local protocol and process-level acceptance; fake execution never starts CST."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4
import pytest
from csttool.configuration import read_json, write_json_atomic
from csttool.execution_contract import StopIntent, ArtifactRef, validate_command
from csttool.hom_scan import ScanInterrupted, AdaptiveHomScanner, ScanPolicy, ScanCheckpointStore, TaskModeResults
from csttool.runner import Runner
from csttool.runner_client import RunnerClient


def command(op, payload=None, **values):
    return {'schema_version': 1, 'request_id': uuid4().hex, 'client_id': 'test-client',
            'operation': op, 'payload': payload or {}, **values}


def wait_until(predicate, timeout=12):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.03)
    raise AssertionError('acceptance condition timed out')


class WaitingExecution:
    calls = 0
    gate = threading.Event()

    def __init__(self, project, stop, run_id, update):
        self.stop = stop

    def run(self, payload):
        type(self).calls += 1
        while not self.stop.is_set() and not self.gate.wait(.01):
            pass

    def request_stop(self):
        self.stop.request()

    def recovery_required(self):
        return False

    def recover(self):
        pass

    def close(self):
        pass


def test_stop_intent_survives_new_object_and_contract_is_json(tmp_path):
    path = tmp_path / 'stop.json'
    StopIntent(path).request()
    with pytest.raises(ScanInterrupted):
        StopIntent(path).check()
    assert json.loads(json.dumps(ArtifactRef('a', 'local', 'file', 'hash').to_mapping()))['node_id'] == 'local'
    with pytest.raises(ValueError):
        validate_command(command('arbitrary-shell'))
    with pytest.raises(ValueError):
        validate_command(command('start', request_id='../escape'))


def test_unique_runner_commands_stop_and_stale_id(tmp_path):
    WaitingExecution.gate.clear()
    WaitingExecution.calls = 0
    runner = Runner(tmp_path, WaitingExecution)
    try:
        with pytest.raises(RuntimeError):
            Runner(tmp_path, WaitingExecution)
        runner.command(command('claim'))
        request = command('start')
        result = runner.command(request)
        assert runner.command(request) == result
        with pytest.raises(ValueError):
            runner.command({**request, 'payload': {'worker_count': 2}})
        with pytest.raises(ValueError):
            runner.command(command('stop', run_id='old-run'))
        with pytest.raises(ValueError):
            runner.command(command('start'))
        runner.command(command('stop', run_id=result['run_id']))
        runner.worker.join(3)
        assert not runner.worker.is_alive()
        assert WaitingExecution.calls == 1
        assert runner.snapshot()['state'] == 'INTERRUPTED'
    finally:
        WaitingExecution.gate.set()
        if runner.worker:
            runner.worker.join(3)
        runner.close()


def test_controller_control_lease_is_not_project_run_ownership(tmp_path):
    runner = Runner(tmp_path, WaitingExecution)
    try:
        runner.command(command('claim'))
        with pytest.raises(ValueError):
            runner.command(command('claim', client_id='other'))
        runner.owner_seen -= 11
        runner.command(command('claim', client_id='other'))
        with pytest.raises(ValueError):
            runner.command(command('shutdown'))
        with pytest.raises(RuntimeError):
            Runner(tmp_path)
    finally:
        runner.close()


def test_durable_start_gap_requires_recovery_not_replay(tmp_path):
    runner = Runner(tmp_path, WaitingExecution)
    runner.close()
    start = command('start')
    write_json_atomic(tmp_path / 'control/commands' / (start['request_id'] + '.json'),
                      {'digest': 'intent', 'command': start, 'result': {'run_id': 'gap'}})
    again = Runner(tmp_path, WaitingExecution)
    try:
        assert again.snapshot()['state'] == 'RECOVERY_REQUIRED'
        assert again.worker is None
        again.command(command('claim'))
        with pytest.raises(ValueError):
            again.command(command('start'))
        again.command(command('recover'))
        again.worker.join(3)
        assert again.snapshot()['state'] == 'IDLE'
    finally:
        again.close()
    third = Runner(tmp_path, WaitingExecution)
    try:
        assert third.snapshot()['state'] == 'IDLE'
    finally:
        third.close()


def test_status_persistence_failure_sets_stop_intent_and_unknown_safety(tmp_path, monkeypatch):
    runner = Runner(tmp_path, WaitingExecution)
    runner.stop_intent = StopIntent()
    def denied(*args):
        raise PermissionError('injected control write failure')
    monkeypatch.setattr('csttool.runner.write_json_atomic', denied)
    try:
        with pytest.raises(PermissionError):
            runner.update(phase='running')
        assert runner.stop_intent.is_set()
        assert runner.snapshot()['state'] == 'RECOVERY_REQUIRED'
        assert runner.snapshot()['session_safety'] == 'unknown'
    finally:
        runner.close()


def test_empty_interval_task_identity_commits_with_checkpoint(tmp_path):
    policy = ScanPolicy(1, 2, 3, window_width=1)
    store = ScanCheckpointStore(tmp_path / 'checkpoint.json')
    report = AdaptiveHomScanner(policy).run(lambda req: TaskModeResults([], f'task-{req.solve_lo}'),
        checkpoint=lambda report, pending: store.save(policy, {}, report, pending))
    recovered, pending = store.load(policy, {})
    assert not pending and recovered.adopted_task_ids == report.adopted_task_ids
    assert len(recovered.adopted_task_ids) == 2


@pytest.fixture
def fake_runner(tmp_path):
    log = (tmp_path / 'fake-runner-output.txt').open('wb')
    process = subprocess.Popen([sys.executable, '-m', 'csttool.runner', '--project', str(tmp_path), '--fake'],
                              cwd=Path(__file__).parents[1], stdout=log, stderr=subprocess.STDOUT)
    client = RunnerClient(tmp_path)
    def ready():
        if process.poll() is not None:
            log.flush()
            raise AssertionError((tmp_path / 'fake-runner-output.txt').read_text(errors='replace'))
        try:
            client.endpoint = None
            return client.status()
        except (OSError, ValueError):
            return False
    wait_until(ready)
    yield client, process
    if process.poll() is None:
        try:
            client.command('claim')
            status = client.status()
            if status['state'] in {'PREPARING', 'RUNNING', 'STOPPING', 'RECOVERING'}:
                client.command('stop', run_id=status['run_id'])
                wait_until(lambda: client.status()['state'] not in {'PREPARING', 'RUNNING', 'STOPPING', 'RECOVERING'})
            if client.status()['state'] == 'RECOVERY_REQUIRED':
                client.command('recover')
                wait_until(lambda: client.status()['state'] == 'IDLE')
            client.command('shutdown')
            process.wait(5)
        finally:
            if process.poll() is None:
                process.kill()  # Only the explicitly synthetic Python acceptance process.
                process.wait(5)
    log.close()


@pytest.mark.parametrize('lost_response', [False, True])
def test_shutdown_wait_confirms_real_runner_release(fake_runner, monkeypatch, lost_response):
    client, process = fake_runner
    runtime = client.status()['runtime']
    assert runtime['pid'] == process.pid
    assert Path(runtime['source_root']) == Path(__file__).resolve().parents[1]
    assert runtime['python']
    assert Path(runtime['cwd']) == Path(__file__).resolve().parents[1]
    original = client.command
    def command_with_loss(op, *args, **kwargs):
        result = original(op, *args, **kwargs)
        if op == 'shutdown' and lost_response:
            raise TimeoutError('shutdown response lost after acceptance')
        return result
    monkeypatch.setattr(client, 'command', command_with_loss)
    assert client.shutdown_and_wait() == {'runner_stopped': True}
    process.wait(5)
    assert process.returncode == 0


def test_shutdown_timeout_never_kills_or_reports_stopped(tmp_path, monkeypatch):
    from csttool.runner_ownership import RunnerOwnership
    lease = RunnerOwnership(tmp_path / 'control/runner.lock').acquire()
    client = RunnerClient(tmp_path)
    monkeypatch.setattr(client, 'connect', lambda **kwargs: {})
    monkeypatch.setattr(client, 'command', lambda *args, **kwargs: {})
    try:
        with pytest.raises(TimeoutError, match='退出尚未确认'):
            client.shutdown_and_wait(timeout=.1)
        assert lease.stream is not None
    finally:
        lease.close()


def test_process_disconnect_reconnect_stop_resume_and_auth(fake_runner, tmp_path):
    client, process = fake_runner
    client.command('claim')
    request_id = uuid4().hex
    payload = {'algorithm': {'fake_delay': .05}, 'worker_count': 1, 'resume': False}
    accepted = client.command('start', payload, request_id=request_id)
    assert client.command('start', payload, request_id=request_id) == accepted
    checkpoint = tmp_path / 'save/csv/hom_scan_checkpoint.json'
    wait_until(checkpoint.exists)
    client.command('stop', run_id=accepted['run_id'])
    wait_until(lambda: client.status()['state'] == 'INTERRUPTED')
    before = read_json(checkpoint)['coverage']['confirmed_frontier']
    fresh = RunnerClient(tmp_path, client.client_id)
    fresh.connect(launch=False)
    fresh.command('start', {**payload, 'resume': True})
    assert process.poll() is None
    wait_until(lambda: fresh.status()['state'] == 'COMPLETED')
    assert read_json(checkpoint)['coverage']['confirmed_frontier'] >= before
    wrong = RunnerClient(tmp_path)
    wrong.endpoint = {**fresh.endpoint, 'token': 'invalid'}
    with pytest.raises((RuntimeError, ValueError)):
        wrong.status()


def test_standard_fake_batch_persists_results_and_refuses_changed_resume(fake_runner, tmp_path):
    client, _ = fake_runner
    client.command('claim')
    tasks = [{'job': f'R-{r}', 'parameters': {'R': r}} for r in (100, 150, 200)]
    client.command('start', {'kind': 'standard', 'tasks': tasks})
    wait_until(lambda: client.status()['state'] not in {'PREPARING', 'RUNNING'})
    status = client.status()
    assert status['state'] == 'COMPLETED', status
    result = read_json(tmp_path / 'save/standard_batch_checkpoint.json')
    assert result['pending_index'] == 3
    assert len(result['results']) == 3
    calls = (tmp_path / 'control/fake-calls.jsonl').read_text().splitlines()
    client.command('start', {'kind': 'standard', 'tasks': tasks, 'resume': True})
    wait_until(lambda: client.status()['state'] == 'COMPLETED')
    assert (tmp_path / 'control/fake-calls.jsonl').read_text().splitlines() == calls


def test_killed_gui_client_does_not_stop_runner(fake_runner, tmp_path):
    client, process = fake_runner
    client.command('claim')
    client.command('release')
    # This child represents a headless GUI transport client, not the Runner.
    code = """import sys,time
from csttool.runner_client import RunnerClient
c=RunnerClient(sys.argv[1]);c.connect(launch=False);c.command('claim')
c.command('start',{'algorithm':{'fake_delay':.08}});c.command('release')
print('submitted',flush=True);time.sleep(60)
"""
    gui = subprocess.Popen([sys.executable, '-c', code, str(tmp_path)],
                           cwd=Path(__file__).parents[1], stdout=subprocess.PIPE, text=True)
    try:
        assert gui.stdout.readline().strip() == 'submitted'
        gui.kill()  # Synthetic client crash; never CST.
        gui.wait(5)
        wait_until(lambda: client.status()['state'] == 'COMPLETED')
        assert process.poll() is None
    finally:
        if gui.poll() is None:
            gui.kill()
            gui.wait(5)


def test_real_qt_gui_process_crash_isolated_from_fake_runner(fake_runner, tmp_path):
    client, process = fake_runner
    client.command('claim')
    client.command('start', {'algorithm': {'fake_delay': .4}})
    client.command('release')
    ready = tmp_path / 'gui-connected.txt'
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    with (tmp_path / 'gui-output.txt').open('wb') as log:
        gui = subprocess.Popen([sys.executable, 'test/support/runner_gui_probe.py',
                                '--project', str(tmp_path), '--ready', str(ready)],
                               cwd=Path(__file__).parents[1], env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            wait_until(ready.exists)
            gui.kill()  # Real Qt GUI process, but all computation is explicitly synthetic.
            gui.wait(5)
            wait_until(lambda: client.status()['state'] == 'COMPLETED')
            assert process.poll() is None
        finally:
            if gui.poll() is None:
                gui.kill()
                gui.wait(5)


def test_runner_crash_restarts_as_recovery_required(fake_runner, tmp_path):
    client, process = fake_runner
    client.command('claim')
    client.command('start', {'algorithm': {'fake_delay': 1}})
    wait_until(lambda: (tmp_path / 'save/csv/hom_scan_checkpoint.json').exists())
    process.kill()  # Fake Runner crash only, with no CST descendants.
    process.wait(5)
    log = (tmp_path / 'restart.txt').open('wb')
    restarted = subprocess.Popen([sys.executable, '-m', 'csttool.runner', '--project', str(tmp_path), '--fake'],
                                cwd=Path(__file__).parents[1], stdout=log, stderr=subprocess.STDOUT)
    fresh = RunnerClient(tmp_path)
    try:
        def ready():
            try:
                fresh.endpoint = None
                return fresh.status()
            except (OSError, ValueError):
                return False
        wait_until(ready)
        assert fresh.status()['state'] == 'RECOVERY_REQUIRED'
        fresh.command('claim')
        fresh.command('recover')
        wait_until(lambda: fresh.status()['state'] == 'IDLE')
        fresh.command('start', {'resume': True, 'algorithm': {'fake_delay': .01}})
        wait_until(lambda: fresh.status()['state'] == 'COMPLETED')
        fresh.command('shutdown')
        restarted.wait(5)
    finally:
        if restarted.poll() is None:
            restarted.kill()
            restarted.wait(5)
        log.close()
