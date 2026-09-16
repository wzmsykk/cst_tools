from uuid import uuid4

import pytest

from csttool.runtime_protocol import (
    Acknowledge,
    Completion,
    CompletionStatus,
    ErrorCode,
    FileProtocol,
    ParameterAssignment,
    ParameterKind,
    ProtocolError,
    Task,
    decode_task,
    encode_task,
    new_session_id,
    validate_ack,
)


def make_task(session_id=None, *, value="2 * Rx"):
    return Task(
        task_id=str(uuid4()),
        session_id=session_id or new_session_id(),
        parameters=(
            ParameterAssignment("Rx", ParameterKind.LITERAL, "90.0"),
            ParameterAssignment("L", ParameterKind.EXPRESSION, value),
        ),
    )


def test_task_round_trip_keeps_literal_and_expression_without_extra_codec():
    task = make_task(value="2 * Rx = L")

    assert decode_task(encode_task(task)) == task


def test_task_rejects_duplicate_parameters_and_newlines():
    session_id = new_session_id()
    duplicate = ParameterAssignment("L", ParameterKind.LITERAL, "1")
    with pytest.raises(ProtocolError, match="unique"):
        Task(str(uuid4()), session_id, (duplicate, duplicate))
    with pytest.raises(ProtocolError, match="parameter value"):
        ParameterAssignment("L", ParameterKind.EXPRESSION, "1\n2")
    with pytest.raises(ProtocolError, match="ASCII"):
        ParameterAssignment("长度", ParameterKind.LITERAL, "1")


def test_file_protocol_publishes_only_final_task(tmp_path):
    protocol = FileProtocol(tmp_path)
    task = make_task()

    destination = protocol.submit(task)

    assert destination.name == f"{task.task_id}.task"
    assert not destination.with_name(destination.name + ".tmp").exists()
    assert decode_task(destination.read_text(encoding="utf-8")) == task
    with pytest.raises(FileExistsError):
        protocol.submit(task)


def test_completion_must_match_task_and_session(tmp_path):
    protocol = FileProtocol(tmp_path)
    task = make_task()
    wrong = Completion(
        task_id=task.task_id,
        session_id=new_session_id(),
        status=CompletionStatus.SUCCESS,
    )
    protocol.publish_completion(wrong)

    with pytest.raises(ProtocolError, match="does not belong"):
        protocol.read_completion(task)


def test_failure_is_not_a_success_and_requires_error_code(tmp_path):
    protocol = FileProtocol(tmp_path)
    task = make_task()
    failure = Completion(
        task_id=task.task_id,
        session_id=task.session_id,
        status=CompletionStatus.FAILURE,
        error_code=ErrorCode.REBUILD_FAILED,
        error_message="Rebuild returned False",
    )
    protocol.publish_completion(failure)

    decoded = protocol.read_completion(task)
    assert decoded == failure
    assert decoded.status is CompletionStatus.FAILURE
    with pytest.raises(ProtocolError, match="requires an error_code"):
        Completion(task.task_id, task.session_id, CompletionStatus.FAILURE)


def test_acknowledge_matches_completion(tmp_path):
    protocol = FileProtocol(tmp_path)
    task = make_task()
    completion = Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS)
    protocol.publish_completion(completion)

    protocol.acknowledge(completion)

    assert protocol.read_ack(completion) == Acknowledge(task.task_id, task.session_id)
    with pytest.raises(ProtocolError, match="does not belong"):
        validate_ack(completion, Acknowledge(task.task_id, new_session_id()))


def test_wait_completion_has_a_bounded_timeout(tmp_path):
    protocol = FileProtocol(tmp_path)
    task = make_task()

    with pytest.raises(TimeoutError, match=task.task_id):
        protocol.wait_completion(task, timeout=0.01, poll_interval=0.001)


class FakeSerialWorker:
    def __init__(self, protocol, session_id):
        self.protocol = protocol
        self.session_id = session_id
        self.waiting_for = None

    def process(self, task):
        if self.waiting_for is not None:
            return False
        wire_task = decode_task(self.protocol.task_path(task.task_id).read_text("utf-8"))
        if wire_task.session_id != self.session_id:
            raise ProtocolError("task belongs to an old worker session")
        completion = Completion(
            wire_task.task_id, wire_task.session_id, CompletionStatus.SUCCESS
        )
        self.protocol.publish_completion(completion)
        self.waiting_for = completion
        return True

    def consume_ack(self):
        if self.waiting_for is None:
            return False
        if self.protocol.read_ack(self.waiting_for) is None:
            return False
        self.waiting_for = None
        return True


def test_fake_worker_does_not_advance_before_ack(tmp_path):
    protocol = FileProtocol(tmp_path)
    session_id = new_session_id()
    worker = FakeSerialWorker(protocol, session_id)
    first = make_task(session_id)
    second = make_task(session_id)
    protocol.submit(first)
    protocol.submit(second)

    assert worker.process(first) is True
    assert worker.process(second) is False
    first_completion = protocol.read_completion(first)
    protocol.acknowledge(first_completion)
    assert worker.consume_ack() is True
    assert worker.process(second) is True


def test_fake_worker_rejects_task_from_old_session(tmp_path):
    protocol = FileProtocol(tmp_path)
    worker = FakeSerialWorker(protocol, new_session_id())
    old_task = make_task(new_session_id())
    protocol.submit(old_task)

    with pytest.raises(ProtocolError, match="old worker session"):
        worker.process(old_task)
