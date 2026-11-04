"""Bounded readiness, owned Python launch and diagnostics. Never launches CST."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import pytest
from csttool import runner_client as transport
from csttool.configuration import read_json,write_json_atomic
from csttool.runner import Runner,serve
from csttool.runner_ownership import RunnerOwnership


class Clock:
    def __init__(self):self.now=0.
    def monotonic(self):return self.now
    def sleep(self,value):self.now+=value


class Process:
    pid=43210
    def __init__(self,code=None):self.code=code
    def poll(self):return self.code
    def kill(self):raise AssertionError('startup must never kill a process')
    terminate=kill


def setup(tmp_path,monkeypatch,code=None):
    clock=Clock();process=Process(code);spawns=[];client=transport.RunnerClient(tmp_path,'startup-test')
    monkeypatch.setattr(transport.time,'monotonic',clock.monotonic)
    monkeypatch.setattr(transport.time,'sleep',clock.sleep)
    def spawn(*a,**kw):spawns.append((a,kw));return process
    monkeypatch.setattr(transport.subprocess,'Popen',spawn)
    return clock,process,spawns,client


def ready(client):
    return dict(instance_id='new-instance',project=str(client.project),state='IDLE',runtime=dict(pid=87654))


def test_timeout_uses_one_budget_leaves_process_and_late_reconnect_uses_same_attempt(tmp_path,monkeypatch):
    clock,process,spawns,client=setup(tmp_path,monkeypatch);timeouts=[]
    def silent(*,timeout):
        timeouts.append(timeout);clock.sleep(timeout);raise TimeoutError('silent endpoint')
    monkeypatch.setattr(client,'status',silent)
    with pytest.raises(transport.RunnerStartupTimeout) as caught:client.connect(timeout=5)
    assert clock.now==pytest.approx(5) and timeouts==[2,2,1]
    assert len(spawns)==1 and process.poll() is None
    attempt=caught.value.diagnostics['attempt_id']
    assert caught.value.diagnostics['startup_state']=='timeout'
    assert caught.value.diagnostics['last_probe_error']['type']=='TimeoutError'
    assert read_json(tmp_path/'control/bootstrap.json')['attempt_id']==attempt
    lease=RunnerOwnership(tmp_path/'control/bootstrap.lock').acquire();lease.close()
    # A second unsuccessful connection cannot replace the still-live attempt.
    with pytest.raises(RuntimeError,match='no automatic restart'):client.connect(timeout=1)
    assert len(spawns)==1
    monkeypatch.setattr(client,'status',lambda **kwargs:ready(client))
    assert client.connect(launch=False)['instance_id']=='new-instance'
    recovered=read_json(tmp_path/'control/bootstrap.json')
    assert recovered['startup_state']=='ready' and recovered['previous_startup_state']=='timeout'
    assert recovered['attempt_id']==attempt and len(spawns)==1
    records=[json.loads(line) for line in (tmp_path/'control/bootstrap.log').read_text().splitlines()]
    assert [r['startup_state'] for r in records][-2:]==['timeout','ready']


def test_launcher_early_exit_is_not_reported_as_full_readiness_timeout(tmp_path,monkeypatch):
    clock,_,spawns,client=setup(tmp_path,monkeypatch,42)
    monkeypatch.setattr(client,'status',lambda **kwargs:(_ for _ in ()).throw(ConnectionError('not listening')))
    with pytest.raises(transport.RunnerStartupError) as caught:client.connect()
    assert caught.value.diagnostics['launcher_exit_code']==42
    assert caught.value.diagnostics['startup_state']=='launcher-exited'
    assert clock.now<15 and len(spawns)==1


def test_initial_silent_probe_exhausts_budget_without_spawn_or_losing_real_error(tmp_path,monkeypatch):
    clock,_,spawns,client=setup(tmp_path,monkeypatch)
    def silent(*,timeout):clock.sleep(timeout);raise TimeoutError('remote read timeout')
    monkeypatch.setattr(client,'status',silent)
    with pytest.raises(transport.RunnerStartupTimeout) as caught:client.connect(timeout=.25)
    assert not spawns and not client.launch_attempted
    assert caught.value.diagnostics['phase']=='before-spawn'
    assert caught.value.diagnostics['probe_count']==1
    assert caught.value.diagnostics['last_probe_error']['message']=='remote read timeout'


def test_http_probe_timeout_reaches_actual_transport_without_changing_command_default(tmp_path,monkeypatch):
    from io import BytesIO
    from types import SimpleNamespace
    client=transport.RunnerClient(tmp_path);calls=[]
    client.endpoint=dict(project=str(tmp_path),port=10001,instance_id='test',token='secret')
    def open(request,*,timeout):
        calls.append(timeout);return BytesIO(b'{"instance_id":"test"}')
    client.opener=SimpleNamespace(open=open)
    client.status(timeout=.125);client.request('/commands',dict(operation='no-op'))
    assert calls==[.125,2]


@pytest.mark.parametrize('body',[b'<html>Forbidden</html>',b'[]',b'null'])
def test_non_json_http_rejection_keeps_http_status_without_echoing_body(tmp_path,body):
    from io import BytesIO
    from types import SimpleNamespace
    from urllib.error import HTTPError
    client=transport.RunnerClient(tmp_path)
    client.endpoint=dict(project=str(tmp_path),port=10001,instance_id='test',token='secret')
    def open(*a,**kw):raise HTTPError('http://127.0.0.1',403,'Forbidden',{},BytesIO(body))
    client.opener=SimpleNamespace(open=open)
    with pytest.raises(HTTPError,match='403'):client.status()


@pytest.mark.parametrize('cannot_write',[False,True])
def test_spawn_error_retains_cause_even_when_diagnostics_cannot_be_written(tmp_path,monkeypatch,cannot_write):
    _,_,_,client=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(client,'status',lambda **kwargs:(_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(transport.subprocess,'Popen',lambda *a,**kw:(_ for _ in ()).throw(OSError('spawn denied')))
    if cannot_write:monkeypatch.setattr(transport,'write_json_atomic',lambda *a:(_ for _ in ()).throw(PermissionError('readonly')))
    with pytest.raises(transport.RunnerStartupError) as caught:client.connect()
    assert caught.value.diagnostics['error']['message']=='spawn denied'
    assert caught.value.diagnostics['startup_state']=='spawn-failed'
    assert ('diagnostic_write_error' in caught.value.diagnostics)==cannot_write


@pytest.mark.parametrize('held',['bootstrap.lock','runner.lock'])
def test_existing_owner_is_waited_for_without_another_launch(tmp_path,monkeypatch,held):
    _,_,spawns,client=setup(tmp_path,monkeypatch);calls=[]
    (tmp_path/'control').mkdir()
    write_json_atomic(tmp_path/'control/bootstrap.json',dict(attempt_id='other-owner'))
    def probe(**kw):
        calls.append(1)
        if len(calls)<3:raise ConnectionError('starting')
        return ready(client)
    monkeypatch.setattr(client,'status',probe)
    lease=RunnerOwnership(tmp_path/'control'/held).acquire()
    try:
        assert client.connect()['state']=='IDLE'
        assert not spawns and not client.launch_attempted
        expected='waiting-other-startup' if held=='bootstrap.lock' else 'waiting-existing-owner'
        assert client.last_startup['phase']==expected
        if held=='bootstrap.lock':assert read_json(tmp_path/'control/bootstrap.json')==dict(attempt_id='other-owner')
    finally:lease.close()


def test_post_lock_recheck_does_not_replace_another_starters_report(tmp_path,monkeypatch):
    _,_,spawns,client=setup(tmp_path,monkeypatch);calls=[]
    existing=dict(attempt_id='winner',startup_state='ready',launcher_pid=123)
    write_json_atomic(tmp_path/'control/bootstrap.json',existing)
    def probe(**kw):
        calls.append(1)
        if len(calls)==1:raise ConnectionError('not ready at initial observation')
        return ready(client)
    monkeypatch.setattr(client,'status',probe)
    assert client.connect()['state']=='IDLE' and not spawns
    assert client.last_startup['phase']=='existing-ready'
    assert read_json(tmp_path/'control/bootstrap.json')==existing


@pytest.mark.parametrize('initial',[b'',b'0',b'previous-lock-marker'])
def test_os_lock_does_not_initialize_or_overwrite_lock_file(tmp_path,initial):
    path=tmp_path/'ownership.lock';path.write_bytes(initial)
    first=RunnerOwnership(path).acquire()
    try:
        with pytest.raises(RuntimeError,match='another controller'):RunnerOwnership(path).acquire()
    finally:first.close()
    second=RunnerOwnership(path).acquire();second.close()
    assert path.read_bytes()==initial


@pytest.mark.parametrize('value',[0,-1,float('inf'),float('nan'),True,'15'])
def test_invalid_readiness_budget_is_rejected_without_launch(tmp_path,monkeypatch,value):
    _,_,spawns,client=setup(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='finite and positive'):client.connect(timeout=value)
    assert not spawns and not (tmp_path/'control').exists()


def test_read_only_connection_never_creates_launch_evidence(tmp_path,monkeypatch):
    _,_,spawns,client=setup(tmp_path,monkeypatch)
    with pytest.raises(FileNotFoundError):client.connect(launch=False)
    assert not spawns and not (tmp_path/'control').exists()


@pytest.mark.parametrize('document',[[],dict(port=True),dict(port=0),dict(port=123,token=None)])
def test_corrupt_endpoint_is_a_diagnosable_value_error(tmp_path,document):
    write_json_atomic(tmp_path/'control/runner.json',document)
    with pytest.raises(ValueError,match='endpoint'):transport.RunnerClient(tmp_path).status()


def test_diagnostics_omit_endpoint_credentials(tmp_path,monkeypatch):
    _,_,_,client=setup(tmp_path,monkeypatch,42)
    def fail(**kwargs):
        client.endpoint=dict(pid=1,port=23,instance_id='old',token='never-record-this')
        raise TimeoutError('unresponsive')
    monkeypatch.setattr(client,'status',fail)
    with pytest.raises(transport.RunnerStartupError):client.connect()
    assert 'never-record-this' not in (tmp_path/'control/bootstrap.json').read_text()


def test_initialization_failure_releases_actual_runner_lock(tmp_path,monkeypatch):
    stages=[]
    monkeypatch.setattr(Runner,'_save_status',lambda self:(_ for _ in ()).throw(OSError('persist failed')))
    with pytest.raises(OSError,match='persist failed'):Runner(tmp_path,startup_observer=stages.append)
    assert 'persist-status' in stages and 'state-ready' not in stages
    lease=RunnerOwnership(tmp_path/'control/runner.lock').acquire();lease.close()


def test_bind_failure_closes_runner_and_records_stage(tmp_path,monkeypatch,capsys):
    from csttool import runner
    monkeypatch.setattr(runner,'ThreadingHTTPServer',lambda *a:(_ for _ in ()).throw(OSError('bind failed')))
    with pytest.raises(OSError,match='bind failed'):serve(tmp_path)
    events=[json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert events[-2]['phase']=='startup-failed' and events[-2]['reason']=='bind failed'
    assert events[-1]['phase']=='ownership-released'
    assert not (tmp_path/'control/runner.json').exists()
    lease=RunnerOwnership(tmp_path/'control/runner.lock').acquire();lease.close()


def test_two_real_clients_share_one_python_runner_and_close_normally(tmp_path,monkeypatch):
    clients=[transport.RunnerClient(tmp_path,'client-'+str(i)) for i in range(2)]
    barrier=threading.Barrier(2);spawns=[];original=transport.subprocess.Popen
    def spawn(*a,**kw):
        p=original(*a,**kw);spawns.append(p);return p
    monkeypatch.setattr(transport.subprocess,'Popen',spawn)
    def connect(client):barrier.wait(timeout=5);return client.connect(timeout=15)
    try:
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(connect,clients))
        assert results[0]['instance_id']==results[1]['instance_id']
        assert len(spawns)==1
        report=read_json(tmp_path/'control/bootstrap.json')
        assert report['startup_state']=='ready' and report['runtime']['pid']==results[0]['runtime']['pid']
    finally:
        if spawns:
            clients[0].shutdown_and_wait(timeout=15)
            for p in spawns:p.wait(timeout=10)
    assert spawns[0].returncode==0
    records=[json.loads(line) for line in (tmp_path/'control/bootstrap.log').read_text().splitlines() if line.startswith('{')]
    events=[r for r in records if r.get('event')=='RUNNER_STARTUP']
    phases=[x['phase'] for x in events]
    assert phases.index('module-ready')<phases.index('runner-ownership')<phases.index('serving')<phases.index('ownership-released')
    assert len({x['pid'] for x in events})==1
