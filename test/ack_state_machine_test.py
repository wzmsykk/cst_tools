from pathlib import Path

import pytest

from csttool.runtime_protocol import Acknowledge, ProtocolError, new_session_id, publish_ack_idempotently
from csttool.managed_cstworker import ManagedAcknowledgmentPending
from csttool.cstmanager import CSTManager, SimulationTask
from test.cstmanager_test import FakeGlobalConfig, FakeProjectConfig


def test_ack_republication_is_idempotent_but_rejects_foreign_identity(tmp_path):
    path = tmp_path / 'current.ack'
    ack = Acknowledge(new_session_id(), new_session_id())
    publish_ack_idempotently(path, ack)
    before = path.read_bytes()
    publish_ack_idempotently(path, ack)
    assert path.read_bytes() == before
    with pytest.raises(ProtocolError):
        publish_ack_idempotently(path, Acknowledge(new_session_id(), ack.session_id))
    assert path.read_bytes() == before


def test_manager_never_replays_completed_ack_pending_task(tmp_path):
    calls = []
    class Worker:
        ID = '0'
        def run_task(self, name, *, params):
            calls.append(name)
            raise ManagedAcknowledgmentPending(tmp_path / 'received.json', 'cannot open ack')
        def stop(self):
            return True
    created = []
    def factory(*args):
        created.append(Worker())
        return created[-1]
    with CSTManager(FakeGlobalConfig(tmp_path), FakeProjectConfig(tmp_path), [],
                    worker_factory=factory, maxTask=1) as manager:
        result = manager.execute(SimulationTask({'nmodes': 1}, 'mode', retry_count=3))
        assert result['AcknowledgmentPending'] is True
        assert manager.stop_requested
    assert calls == ['mode']
    assert len(created) == 1


def test_vba_blocked_ack_waits_for_stop_without_reentering_solver():
    source = (Path(__file__).parents[1] / 'data/runtime_managed_worker_v1_main.vb').read_text(encoding='utf-8')
    wait = source.split('WaitForAck:', 1)[1].split('CloseWorker:', 1)[0]
    assert 'If Not ackBlocked And Dir' in wait
    assert 'GoTo AckWaitTick' in wait
    assert 'failure:ACK_BLOCKED:' in wait
    assert 'EigenmodeSolver.Start' not in wait
    assert 'For i = 1 To 6000' not in wait
    assert 'If Dir("%STOP_REQUEST_PATH%")' in wait
