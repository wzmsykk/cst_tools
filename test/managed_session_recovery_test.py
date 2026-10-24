from threading import Thread
import time

from csttool.managed_session_recovery import recover_and_stop_session
from csttool.runtime_protocol import (
    Completion,
    CompletionStatus,
    FileProtocol,
    StopAcknowledge,
    atomic_publish,
    encode_completion,
    encode_stop_ack,
    new_session_id,
)
import pytest


def test_recovery_acks_preserved_completion_and_waits_for_stop_ack(tmp_path):
    session_id = new_session_id()
    task_id = new_session_id()
    protocol = FileProtocol(tmp_path)

    def worker_side():
        while not (protocol.root / "stop.request").exists():
            time.sleep(0.01)
        atomic_publish(
            protocol.root / "current.completion",
            encode_completion(
                Completion(task_id, session_id, CompletionStatus.SUCCESS)
            ),
        )
        while not (protocol.root / "current.ack").exists():
            time.sleep(0.01)
        atomic_publish(
            protocol.root / "stop.ack",
            encode_stop_ack(StopAcknowledge(session_id)),
        )

    thread = Thread(target=worker_side)
    thread.start()
    completion = recover_and_stop_session(
        protocol.root, session_id, timeout=2, poll_interval=0.01
    )
    thread.join(2)

    assert completion is not None
    assert completion.task_id == task_id
    assert (protocol.root / "current.ack").exists()
    assert not thread.is_alive()


def test_existing_wrong_stop_request_is_rejected_without_waiting(tmp_path, monkeypatch):
    protocol = FileProtocol(tmp_path)
    protocol.request_stop(new_session_id())
    before = (tmp_path / 'stop.request').read_bytes()
    monkeypatch.setattr('csttool.managed_session_recovery.time.sleep',
                        lambda value: pytest.fail('invalid request must not enter polling'))
    with pytest.raises(ValueError, match='another'):
        recover_and_stop_session(tmp_path, new_session_id(), timeout=1)
    assert (tmp_path / 'stop.request').read_bytes() == before


def test_observed_peer_exit_ends_wait_without_inventing_ack(tmp_path):
    session_id = new_session_id()
    completion = recover_and_stop_session(tmp_path, session_id, timeout=1,
                                          peer_exited=lambda: True)
    assert completion is None
    assert not (tmp_path / 'stop.ack').exists()
