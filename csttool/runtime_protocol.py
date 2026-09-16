"""Minimal file protocol for the Python/CST VBA worker boundary.

Only the safety properties needed by the current local Warm CST workflow live
here: task/session identity, atomic publication, completion, and acknowledgement.
Result discovery and retry policy remain outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import time
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4


TASK_MAGIC = "CST_TASK_V1"
COMPLETION_MAGIC = "CST_COMPLETION_V1"
ACK_MAGIC = "CST_ACK_V1"
STOP_REQUEST_MAGIC = "CST_STOP_REQUEST_V1"
STOP_ACK_MAGIC = "CST_STOP_ACK_V1"


class ProtocolError(ValueError):
    """The peer supplied a malformed or unrelated protocol message."""


class StoppableWorker(Protocol):
    """Minimal lifecycle surface required by timeout handling."""

    def stop(self) -> Any:
        ...


class ParameterKind(str, Enum):
    LITERAL = "literal"
    EXPRESSION = "expression"


class CompletionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class ErrorCode(str, Enum):
    INVALID_TASK = "INVALID_TASK"
    REBUILD_FAILED = "REBUILD_FAILED"
    SOLVER_FAILED = "SOLVER_FAILED"
    RESULT_FLUSH_FAILED = "RESULT_FLUSH_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class ParameterAssignment:
    name: str
    kind: ParameterKind
    value: str

    def __post_init__(self) -> None:
        _validate_line("parameter name", self.name)
        _validate_line("parameter value", self.value)
        if not isinstance(self.kind, ParameterKind):
            object.__setattr__(self, "kind", ParameterKind(self.kind))


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    session_id: str
    parameters: tuple[ParameterAssignment, ...]

    def __post_init__(self) -> None:
        _validate_uuid("task_id", self.task_id)
        _validate_uuid("session_id", self.session_id)
        object.__setattr__(self, "parameters", tuple(self.parameters))
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ProtocolError("parameter names must be unique")

    @classmethod
    def create(
        cls,
        session_id: str,
        parameters: Mapping[str, object],
        *,
        expression_names: frozenset[str] = frozenset(),
    ) -> "Task":
        assignments = tuple(
            ParameterAssignment(
                name=name,
                kind=(
                    ParameterKind.EXPRESSION
                    if name in expression_names
                    else ParameterKind.LITERAL
                ),
                value=str(value),
            )
            for name, value in parameters.items()
        )
        return cls(str(uuid4()), session_id, assignments)


@dataclass(frozen=True, slots=True)
class Completion:
    task_id: str
    session_id: str
    status: CompletionStatus
    error_code: ErrorCode | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        _validate_uuid("task_id", self.task_id)
        _validate_uuid("session_id", self.session_id)
        if not isinstance(self.status, CompletionStatus):
            object.__setattr__(self, "status", CompletionStatus(self.status))
        if self.error_code is not None and not isinstance(self.error_code, ErrorCode):
            object.__setattr__(self, "error_code", ErrorCode(self.error_code))
        if self.error_message is not None:
            _validate_line("error_message", self.error_message)
        if self.status is CompletionStatus.SUCCESS:
            if self.error_code is not None or self.error_message is not None:
                raise ProtocolError("successful completion cannot contain an error")
        elif self.error_code is None:
            raise ProtocolError("failed completion requires an error_code")


@dataclass(frozen=True, slots=True)
class Acknowledge:
    task_id: str
    session_id: str

    def __post_init__(self) -> None:
        _validate_uuid("task_id", self.task_id)
        _validate_uuid("session_id", self.session_id)


@dataclass(frozen=True, slots=True)
class StopRequest:
    session_id: str

    def __post_init__(self) -> None:
        _validate_uuid("session_id", self.session_id)


@dataclass(frozen=True, slots=True)
class StopAcknowledge:
    session_id: str

    def __post_init__(self) -> None:
        _validate_uuid("session_id", self.session_id)


def new_session_id() -> str:
    return str(uuid4())


def encode_task(task: Task) -> str:
    fields = [
        ("task_id", task.task_id),
        ("session_id", task.session_id),
        ("parameter_count", str(len(task.parameters))),
    ]
    for index, parameter in enumerate(task.parameters):
        fields.extend((
            (f"param.{index}.name", parameter.name),
            (f"param.{index}.kind", parameter.kind.value),
            (f"param.{index}.value", parameter.value),
        ))
    return _encode(TASK_MAGIC, fields)


def decode_task(text: str) -> Task:
    fields = _decode(text, TASK_MAGIC)
    count = _integer(fields, "parameter_count")
    parameters = tuple(
        ParameterAssignment(
            _required(fields, f"param.{index}.name"),
            ParameterKind(_required(fields, f"param.{index}.kind")),
            _required(fields, f"param.{index}.value"),
        )
        for index in range(count)
    )
    _reject_unknown(fields, {
        "task_id", "session_id", "parameter_count",
        *(f"param.{index}.{field}" for index in range(count) for field in ("name", "kind", "value")),
    })
    return Task(
        task_id=_required(fields, "task_id"),
        session_id=_required(fields, "session_id"),
        parameters=parameters,
    )


def encode_completion(completion: Completion) -> str:
    fields = [
        ("task_id", completion.task_id),
        ("session_id", completion.session_id),
        ("status", completion.status.value),
    ]
    if completion.error_code is not None:
        fields.append(("error_code", completion.error_code.value))
    if completion.error_message is not None:
        fields.append(("error_message", completion.error_message))
    return _encode(COMPLETION_MAGIC, fields)


def decode_completion(text: str) -> Completion:
    fields = _decode(text, COMPLETION_MAGIC)
    _reject_unknown(
        fields, {"task_id", "session_id", "status", "error_code", "error_message"}
    )
    error_code = fields.get("error_code")
    return Completion(
        task_id=_required(fields, "task_id"),
        session_id=_required(fields, "session_id"),
        status=CompletionStatus(_required(fields, "status")),
        error_code=ErrorCode(error_code) if error_code is not None else None,
        error_message=fields.get("error_message"),
    )


def encode_ack(ack: Acknowledge) -> str:
    return _encode(ACK_MAGIC, (("task_id", ack.task_id), ("session_id", ack.session_id)))


def decode_ack(text: str) -> Acknowledge:
    fields = _decode(text, ACK_MAGIC)
    _reject_unknown(fields, {"task_id", "session_id"})
    return Acknowledge(
        task_id=_required(fields, "task_id"),
        session_id=_required(fields, "session_id"),
    )


def encode_stop_request(request: StopRequest) -> str:
    return _encode(STOP_REQUEST_MAGIC, (("session_id", request.session_id),))


def decode_stop_request(text: str) -> StopRequest:
    fields = _decode(text, STOP_REQUEST_MAGIC)
    _reject_unknown(fields, {"session_id"})
    return StopRequest(_required(fields, "session_id"))


def encode_stop_ack(ack: StopAcknowledge) -> str:
    return _encode(STOP_ACK_MAGIC, (("session_id", ack.session_id),))


def decode_stop_ack(text: str) -> StopAcknowledge:
    fields = _decode(text, STOP_ACK_MAGIC)
    _reject_unknown(fields, {"session_id"})
    return StopAcknowledge(_required(fields, "session_id"))


def validate_completion(task: Task, completion: Completion) -> None:
    if (completion.task_id, completion.session_id) != (task.task_id, task.session_id):
        raise ProtocolError("completion does not belong to this task and session")


def validate_ack(completion: Completion, ack: Acknowledge) -> None:
    if (ack.task_id, ack.session_id) != (completion.task_id, completion.session_id):
        raise ProtocolError("acknowledge does not belong to this completion")


class FileProtocol:
    """Minimal local transport; no generic transport abstraction is introduced."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.inbox = self.root / "inbox"
        self.completed = self.root / "completed"
        self.acks = self.root / "ack"
        for directory in (self.inbox, self.completed, self.acks):
            directory.mkdir(parents=True, exist_ok=True)

    def submit(self, task: Task) -> Path:
        return atomic_publish(self.inbox / f"{task.task_id}.task", encode_task(task))

    def task_path(self, task_id: str) -> Path:
        _validate_uuid("task_id", task_id)
        return self.inbox / f"{task_id}.task"

    def publish_completion(self, completion: Completion) -> Path:
        return atomic_publish(
            self.completed / f"{completion.task_id}.completion",
            encode_completion(completion),
        )

    def read_completion(self, task: Task) -> Completion | None:
        path = self.completed / f"{task.task_id}.completion"
        if not path.exists():
            return None
        completion = decode_completion(path.read_text(encoding="utf-8"))
        validate_completion(task, completion)
        return completion

    def wait_completion(
        self,
        task: Task,
        timeout: float,
        *,
        poll_interval: float = 0.1,
    ) -> Completion:
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("timeout and poll_interval must be positive")
        deadline = time.monotonic() + timeout
        while True:
            completion = self.read_completion(task)
            if completion is not None:
                return completion
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for task {task.task_id}")
            time.sleep(min(poll_interval, remaining))

    def acknowledge(self, completion: Completion) -> Path:
        ack = Acknowledge(completion.task_id, completion.session_id)
        return atomic_publish(self.acks / f"{ack.task_id}.ack", encode_ack(ack))

    def read_ack(self, completion: Completion) -> Acknowledge | None:
        path = self.acks / f"{completion.task_id}.ack"
        if not path.exists():
            return None
        ack = decode_ack(path.read_text(encoding="utf-8"))
        validate_ack(completion, ack)
        return ack

    def request_stop(self, session_id: str) -> Path:
        return atomic_publish(
            self.root / "stop.request",
            encode_stop_request(StopRequest(session_id)),
        )

    def read_stop_request(self, session_id: str) -> StopRequest | None:
        path = self.root / "stop.request"
        if not path.exists():
            return None
        request = decode_stop_request(path.read_text(encoding="utf-8"))
        if request.session_id != session_id:
            raise ProtocolError("stop request belongs to another worker session")
        return request

    def read_stop_ack(self, session_id: str) -> StopAcknowledge | None:
        path = self.root / "stop.ack"
        if not path.exists():
            return None
        ack = decode_stop_ack(path.read_text(encoding="utf-8"))
        if ack.session_id != session_id:
            raise ProtocolError("stop acknowledge belongs to another worker session")
        return ack


def wait_completion_or_stop(
    protocol: FileProtocol,
    task: Task,
    timeout: float,
    worker: StoppableWorker,
    *,
    poll_interval: float = 0.1,
) -> Completion:
    """Wait for one completion and stop its worker if the wait times out."""
    try:
        return protocol.wait_completion(
            task,
            timeout,
            poll_interval=poll_interval,
        )
    except TimeoutError as timeout_error:
        try:
            worker.stop()
        except Exception as stop_error:
            raise timeout_error from stop_error
        raise


def atomic_publish(destination: str | Path, text: str) -> Path:
    """Publish exactly once; readers never observe a partially written message."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if destination.exists() or temporary.exists():
        raise FileExistsError(destination)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _encode(magic: str, fields) -> str:
    lines = [magic]
    for key, value in fields:
        _validate_line("field name", key)
        _validate_line(key, value)
        lines.extend((key, value))
    return "\n".join(lines) + "\n"


def _decode(text: str, magic: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != magic:
        raise ProtocolError(f"expected {magic}")
    body = lines[1:]
    if len(body) % 2:
        raise ProtocolError("message contains an incomplete key/value pair")
    fields: dict[str, str] = {}
    for index in range(0, len(body), 2):
        key, value = body[index], body[index + 1]
        if not key or key in fields:
            raise ProtocolError(f"duplicate or empty field: {key!r}")
        fields[key] = value
    return fields


def _required(fields: Mapping[str, str], key: str) -> str:
    try:
        value = fields[key]
    except KeyError as exc:
        raise ProtocolError(f"missing required field: {key}") from exc
    if value == "":
        raise ProtocolError(f"empty required field: {key}")
    return value


def _integer(fields: Mapping[str, str], key: str) -> int:
    try:
        value = int(_required(fields, key))
    except ValueError as exc:
        raise ProtocolError(f"field {key} is not an integer") from exc
    if value < 0:
        raise ProtocolError(f"field {key} must not be negative")
    return value


def _reject_unknown(fields: Mapping[str, str], allowed: set[str]) -> None:
    unknown = set(fields) - allowed
    if unknown:
        raise ProtocolError(f"unknown fields: {', '.join(sorted(unknown))}")


def _validate_line(label: str, value: object) -> None:
    if not isinstance(value, str) or value == "" or "\r" in value or "\n" in value:
        raise ProtocolError(f"invalid {label}: {value!r}")
    if not value.isascii():
        raise ProtocolError(f"{label} must be ASCII in protocol v1")


def _validate_uuid(label: str, value: str) -> None:
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProtocolError(f"invalid {label}: {value!r}") from exc
    if str(parsed) != value:
        raise ProtocolError(f"{label} must use canonical UUID form")
