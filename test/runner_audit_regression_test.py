"""Audit regressions: real loopback HTTP faults, synthetic execution only."""
from concurrent.futures import Future, ThreadPoolExecutor
import json
from pathlib import Path
import threading
from uuid import uuid4

import pytest
from GUI.application_service import ConfigurationService, ApplicationBackend
from GUI.runner_backend import RunnerBackend
from GUI.runner_controller import RunnerController
from GUI.run_controller import RunState
from csttool.event_replay import read_events
from csttool.runner import Runner, serve
from csttool.runner_client import RunnerClient
from csttool.scan_settings import default_hom_settings
from test.runner_test import command, WaitingExecution, fake_runner, wait_until
from test.gui_runner_test import app, wait, Client


@pytest.fixture
def runner(tmp_path):
    WaitingExecution.gate.clear()
    WaitingExecution.calls = 0
    instance = Runner(tmp_path, WaitingExecution)
    instance.command(command('claim'))
    yield instance
    WaitingExecution.gate.set()
    if instance.worker:
        instance.worker.join(3)
    instance.close()


def test_cancel_before_arrival_and_restart_tombstone(runner):
    start = command('start')
    runner.command(command('cancel_start', {'start_request_id': start['request_id']}))
    assert runner.command(start)['cancelled']
    assert runner.command_record(start['request_id'])['result']['run_id'] is None
    assert runner.worker is None
    runner.close()
    again = Runner(runner.project, WaitingExecution)
    try:
        assert again.snapshot()['state'] == 'IDLE'
        again.command(command('claim'))
        assert again.command(start)['cancelled']
    finally:
        again.close()


def test_old_start_cancel_does_not_stop_new_run(runner):
    first = command('start')
    runner.command(first)
    WaitingExecution.gate.set()
    runner.worker.join(3)
    WaitingExecution.gate.clear()
    second = runner.command(command('start'))
    runner.command(command('cancel_start', {'start_request_id': first['request_id']}))
    assert runner.status['run_id'] == second['run_id']
    assert not runner.stop_intent.is_set()
    assert runner.snapshot()['state'] in {'PREPARING', 'RUNNING'}


def test_expired_heartbeat_and_claim_replay_cannot_steal_lease(runner):
    claim = command('claim')
    runner.command(claim)
    runner.owner_seen -= 11
    before = runner.owner_seen
    runner.heartbeat('test-client')
    assert runner.owner_seen == before
    assert not runner.snapshot()['control_lease_valid']
    runner.command(command('claim', client_id='other'))
    with pytest.raises(ValueError):
        runner.command(claim)
    assert runner.owner_client == 'other'


def test_simultaneous_claim_has_one_winner(runner):
    runner.owner_seen -= 11
    def claim(name):
        try:
            runner.command(command('claim', client_id=name))
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(claim, ['first', 'second'])) == 1


@pytest.mark.parametrize('length', [65535, 65536, 70000, 3000000])
def test_large_event_progress_is_bounded_and_following_record_visible(tmp_path, length):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(json.dumps({'message': '中' * length}, ensure_ascii=False).encode() + b'\n'
                     + b'{"message":"after"}\n')
    cursor = 0
    seen = []
    for _ in range(60):
        result = read_events(path, cursor)
        offset = cursor.get('offset', 0) if isinstance(cursor, dict) else cursor
        assert 0 <= result['cursor']['offset'] - offset <= 262144
        seen.extend(result['events'])
        cursor = result['cursor']
        if any(event.get('message') == 'after' for event in seen):
            break
    assert any(event.get('message') == 'after' for event in seen)
    assert sum(event.get('event') == 'LOG_RECORD_SKIPPED' for event in seen) == 1
    assert path.stat().st_size > length


def test_partial_tail_invalid_record_and_rotation(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(b'{"message":"tail"}')
    cursor = read_events(path)['cursor']
    assert cursor['offset'] == 0
    with path.open('ab') as stream:
        stream.write(b'\ninvalid\n{"message":"next"}\n')
    result = read_events(path, cursor)
    assert [v.get('message') for v in result['events']] == ['tail', '日志记录损坏；请查看原始 JSONL', 'next']
    path.rename(tmp_path / 'old.jsonl')
    path.write_text('{"message":"rotated"}\n', encoding='utf-8')
    assert read_events(path, result['cursor'])['events'][0]['message'] == 'rotated'


def controller_for(client):
    backend = RunnerBackend()
    backend.project = str(client.project)
    backend.client = client
    controller = RunnerController(ConfigurationService(backend))
    controller.timer.setInterval(15)
    controller.set_inputs_ready(True)
    return controller


class DropStartBody:
    """Receive real HTTP response headers, then close without reading its body."""
    def __init__(self, opener):
        self.opener = opener
        self.dropped = False

    def open(self, request, **options):
        response = self.opener.open(request, **options)
        if request.data and json.loads(request.data)['operation'] == 'start' and not self.dropped:
            self.dropped = True
            response.close()
            raise TimeoutError('injected HTTP start response body loss')
        return response


def test_http_start_response_lost_stop_is_preserved_and_delivered(app, fake_runner):
    client, process = fake_runner
    client.opener = DropStartBody(client.opener)
    controller = controller_for(client)
    controller.backend.algorithm['fake_delay'] = .2
    try:
        assert controller.start()
        assert controller.request_stop()
        wait(app, lambda: client.opener.dropped)
        wait(app, lambda: not controller.has_active_work)
        assert client.status()['state'] == 'INTERRUPTED'
        starts = [json.loads(path.read_text()) for path in (client.project / 'control/commands').glob('*.json')]
        starts = [record for record in starts if record['command']['operation'] == 'start']
        assert len(starts) == 1
        assert client.command_record(controller.start_request_id)['result']['run_id'] == controller.run_id
        assert not client.stop_request_path.exists()
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


def test_controller_restart_recovers_persisted_stop_intent(app, fake_runner):
    client, process = fake_runner
    client.command('claim')
    request_id = uuid4().hex
    accepted = client.command('start', {'algorithm': {'fake_delay': .2}}, request_id=request_id)
    client.save_stop_request(request_id)
    fresh = RunnerClient(client.project, client.client_id)
    controller = controller_for(fresh)
    try:
        wait(app, lambda: not controller.has_active_work)
        assert fresh.status()['state'] == 'INTERRUPTED'
        assert fresh.status()['run_id'] == accepted['run_id']
        assert not fresh.stop_request_path.exists()
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


def test_gui_claim_reachable_from_readonly(app, fake_runner):
    owner, process = fake_runner
    owner.command('claim')
    other = RunnerClient(owner.project)
    controller = controller_for(other)
    try:
        wait(app, lambda: controller.read_only)
        # Valid owner is rejected, then release makes the GUI request succeed.
        assert controller.request_control()
        wait(app, lambda: controller.unknown)
        owner.command('release')
        wait(app, lambda: not controller.unknown)
        assert controller.request_control()
        wait(app, lambda: other.status()['owner_client'] == other.client_id and not controller.read_only)
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


@pytest.mark.parametrize('error', [False, True])
def test_project_switch_discards_stale_success_and_error_including_aba(app, tmp_path, error):
    a = Client(str(tmp_path / 'a'))
    b = Client(str(tmp_path / 'b'))
    launches = []
    original = b.connect
    def connect(**kwargs):
        launches.append(kwargs['launch'])
        return original(**kwargs)
    b.connect = connect
    controller = controller_for(a)
    controller.timer.stop()
    stale = Future()
    controller.future = stale
    controller.instance = 'old-instance'
    controller.backend.client = b
    controller.backend.project = b.project
    controller.poll()
    assert controller.instance is None
    if error:
        stale.set_exception(OSError('old project failure'))
    else:
        stale.set_result((a.connect(), a.events()))
    controller.poll()
    controller.timer.start(10)
    try:
        wait(app, lambda: bool(launches) and controller.instance is not None)
        assert launches[0] is True
        assert not controller.unknown
        controller.timer.stop()
        if controller.future:
            wait_until(controller.future.done)
            controller.poll()
        controller.backend.client = a
        controller.backend.project = a.project
        controller.poll()
        assert controller.generation == 2
        assert controller.last_error != 'old project failure'
    finally:
        controller.detach()


def test_draft_does_not_impersonate_execution_backend():
    draft = RunnerBackend()
    assert draft.algorithm == default_hom_settings()
    assert not isinstance(draft, ApplicationBackend)
    assert not hasattr(draft, 'execute_run')
    ConfigurationService(draft)
    with pytest.raises(ValueError):
        draft.update_algorithm_settings({'mesh_cells_per_wavelength': 0})
    assert draft.algorithm['mesh_cells_per_wavelength'] == 20


@pytest.mark.parametrize('size', [65535, 65536, 65537])
def test_exact_event_byte_boundaries(tmp_path, size):
    path = tmp_path / 'events.jsonl'
    prefix, suffix = b'{"message":"', b'"}\n'
    path.write_bytes(prefix + b'a' * (size-len(prefix)-len(suffix)) + suffix + b'{"message":"after"}\n')
    events = read_events(path)['events']
    assert events[-1]['message'] == 'after'
    assert (events[0].get('event') == 'LOG_RECORD_SKIPPED') == (size > 65536)


def test_aba_old_exception_never_updates_current_generation(app, tmp_path):
    first = Client(str(tmp_path / 'a'))
    controller = controller_for(first)
    controller.timer.stop()
    stale = Future()
    controller.future = stale
    controller.backend.client = Client(str(tmp_path / 'b'))
    controller.backend.project = controller.backend.client.project
    controller.poll()
    controller.backend.client = Client(first.project)
    controller.backend.project = first.project
    controller.poll()
    stale.set_exception(OSError('first A late error'))
    controller.poll()
    try:
        assert controller.generation == 2
        assert not controller.unknown
        assert controller.last_error is None
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


def test_real_http_server_delayed_start_response_times_out_then_stop_reconciles(app, tmp_path, monkeypatch):
    accepted = threading.Event()
    release_response = threading.Event()
    original = Runner.command
    def delayed(self, request):
        result = original(self, request)
        if request['operation'] == 'start':
            accepted.set()
            release_response.wait(4)
        return result
    monkeypatch.setattr(Runner, 'command', delayed)
    thread = threading.Thread(target=serve, args=(tmp_path, WaitingExecution))
    WaitingExecution.gate.clear()
    thread.start()
    client = RunnerClient(tmp_path)
    def ready():
        try:
            return client.status()
        except (OSError, ValueError):
            return False
    wait_until(ready)
    controller = controller_for(client)
    try:
        assert controller.start()
        wait(app, accepted.is_set)
        assert controller.request_stop()
        wait(app, lambda: controller.unknown)  # urllib's actual two-second socket timeout.
        wait(app, lambda: not controller.has_active_work)
        assert client.status()['state'] == 'INTERRUPTED'
        assert not client.stop_request_path.exists()
        records = list((tmp_path / 'control/commands').glob('*.json'))
        assert sum(json.loads(p.read_text())['command']['operation'] == 'start' for p in records) == 1
    finally:
        release_response.set()
        controller.detach()
        controller.pool.shutdown(wait=True)
        WaitingExecution.gate.set()
        client.command('claim')
        client.command('shutdown')
        thread.join(5)
        assert not thread.is_alive()


@pytest.mark.parametrize('fault', ['not-sent', 'cancel-response-lost'])
def test_http_not_sent_late_start_and_lost_cancel_response(app, fake_runner, fault):
    client, process = fake_runner
    class FaultTransport:
        dropped = False
        def __init__(self, opener):
            self.opener = opener
        def open(self, request, **kwargs):
            op = json.loads(request.data)['operation'] if request.data else None
            if not self.dropped and fault == 'not-sent' and op == 'start':
                self.dropped = True
                raise TimeoutError('injected before HTTP start transmission')
            response = self.opener.open(request, **kwargs)
            if not self.dropped and fault == 'cancel-response-lost' and op == 'cancel_start':
                self.dropped = True
                response.close()
                raise TimeoutError('injected cancellation response loss')
            return response
    client.opener = FaultTransport(client.opener)
    controller = controller_for(client)
    controller.backend.algorithm['fake_delay'] = .2
    payload = controller.backend.run_payload(False, 1)
    try:
        assert controller.start()
        start_id = controller.start_request_id
        assert controller.request_stop()
        wait(app, lambda: client.opener.dropped and not controller.has_active_work)
        if fault == 'not-sent':
            assert client.status()['state'] == 'IDLE'
            client.command('claim')
            result = client.command('start', payload, request_id=start_id)
            assert result['cancelled'] and not result['accepted']
            assert not (client.project / 'control/fake-calls.jsonl').exists()
        else:
            assert client.status()['state'] == 'INTERRUPTED'
        assert not client.stop_request_path.exists()
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


def test_gui_can_claim_expired_owner_without_reviving_heartbeat(app, runner):
    class DirectClient(Client):
        client_id = 'new-gui'
        def connect(self, **kwargs):
            runner.heartbeat(self.client_id)
            return runner.snapshot()
        def command(self, op, payload=None, **kwargs):
            return runner.command(command(op, payload, client_id=self.client_id, **kwargs))
    client = DirectClient(str(runner.project))
    controller = controller_for(client)
    runner.owner_seen -= 11
    try:
        wait(app, lambda: controller.read_only)
        assert not runner.snapshot()['control_lease_valid']
        assert controller.request_control()
        wait(app, lambda: not controller.read_only)
        assert runner.owner_client == client.client_id
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


def test_pending_stop_allows_required_recovery_before_reconciliation(app, runner):
    from csttool.configuration import write_json_atomic
    start = command('start')
    write_json_atomic(runner.control / 'commands' / (start['request_id'] + '.json'),
        dict(digest='crash-gap', command=start, result=dict(run_id='unfinished-run')))
    runner.update(state='RECOVERY_REQUIRED', run_id='unfinished-run')
    class DirectClient(Client):
        client_id = 'test-client'
        def connect(self, **kwargs):
            return runner.snapshot()
        def command(self, op, payload=None, **kwargs):
            return runner.command(command(op, payload, client_id=self.client_id, **kwargs))
    client = DirectClient(str(runner.project))
    client.save_stop_request(start['request_id'])
    controller = controller_for(client)
    try:
        wait(app, lambda: controller.state is RunState.RECOVERY_REQUIRED)
        assert controller.stop_after_start
        assert not controller.pending
        assert controller.request_recovery()
        wait(app, lambda: not controller.has_active_work)
        assert runner.snapshot()['state'] == 'IDLE'
        assert client.pending_stop_request() is None
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)
