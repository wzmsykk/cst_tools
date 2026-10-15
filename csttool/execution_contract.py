"""Small JSON contracts shared by local control and future node execution."""
from dataclasses import dataclass, asdict
from pathlib import Path
import threading
from typing import TypedDict, Protocol
from .configuration import write_json_atomic
from .hom_scan import ScanInterrupted, ScanReport


class RunnerSnapshot(TypedDict):
    """Wire DTO; recovery and control facts originate only in the Runner."""
    instance_id: str
    project_id: str
    project: str
    run_id: str | None
    state: str
    owner_client: str | None
    control_lease_valid: bool
    control_lease_remaining: float
    control_revision: int


class ExecutionControl(Protocol):
    """Client control port, not an in-process execution backend."""
    client_id: str
    project: Path
    def connect(self, *, launch: bool = True) -> RunnerSnapshot: ...
    def events(self, cursor=0): ...
    def command(self, operation, payload=None, *, run_id=None, request_id=None): ...


class StopIntent:
    """An explicit run-scoped stop, valid before a Manager exists."""
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.event = threading.Event()

    def request(self):
        self.event.set()
        if self.path:
            write_json_atomic(self.path, {'schema_version': 1, 'stop_requested': True})

    def is_set(self):
        return self.event.is_set() or bool(self.path and self.path.exists())

    def check(self):
        if self.is_set():
            raise ScanInterrupted(ScanReport(), [])


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    node_id: str
    path: str
    sha256: str

    def to_mapping(self):
        return asdict(self)


def validate_command(value):
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('unsupported command schema')
    for name in ('request_id', 'client_id'):
        text = value.get(name)
        if not isinstance(text, str) or not 1 <= len(text) <= 100 or not all(
                c.isalnum() or c in '-_' for c in text):
            raise ValueError('invalid ' + name)
    if value.get('operation') not in {'claim', 'release', 'start', 'stop', 'cancel_start', 'recover', 'shutdown'}:
        raise ValueError('unknown operation')
    if not isinstance(value.get('payload', {}), dict):
        raise ValueError('payload must be an object')
    return value
