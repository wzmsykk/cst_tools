"""Discovery and protocol recovery for managed CST sessions in one project."""

from __future__ import annotations

import configparser
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from .managed_session_recovery import recover_and_stop_session
from .runtime_protocol import atomic_publish, decode_completion


@dataclass(frozen=True, slots=True)
class ManagedSessionRecord:
    worker_id: str
    session_id: str
    root: Path
    marker: str
    has_completion: bool
    has_ack: bool
    has_stop_ack: bool
    process_id: int | None
    process_alive: bool | None
    recovery_disposition: str | None

    @property
    def needs_recovery(self) -> bool:
        if (
            self.recovery_disposition == "standard-stop"
            and self.process_alive is not True
        ):
            return False
        if (
            self.recovery_disposition == "abandoned-dead"
            and self.process_alive is False
        ):
            return False
        if self.has_completion and not self.has_ack:
            return True
        return self.marker not in {"stopped", "stopped-with-completion"} or not self.has_stop_ack


def _read_recovery_disposition(session_root: Path) -> str | None:
    receipt = session_root / "recovery.json"
    if not receipt.is_file():
        return None
    try:
        return str(json.loads(receipt.read_text(encoding="utf-8"))["disposition"])
    except (KeyError, OSError, TypeError, ValueError):
        return None


def _write_recovery_receipt(
    record: ManagedSessionRecord,
    disposition: str,
    *,
    completion=None,
) -> None:
    document = {
        "schema_version": 1,
        "session_id": record.session_id,
        "worker_id": record.worker_id,
        "disposition": disposition,
        "recovered_at": datetime.now(timezone.utc).isoformat(),
        "process_id": record.process_id,
        "completion_task_id": getattr(completion, "task_id", None),
        "completion_status": (
            getattr(getattr(completion, "status", None), "value", None)
        ),
    }
    atomic_publish(
        record.root / "recovery.json",
        json.dumps(document, ensure_ascii=False, indent=2),
    )


def _read_completion(record: ManagedSessionRecord):
    path = record.root / "protocol" / "current.completion"
    if not path.is_file():
        return None
    try:
        completion = decode_completion(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return completion if completion.session_id == record.session_id else None


def _wait_for_process_exit(record: ManagedSessionRecord, timeout: float) -> None:
    if record.process_id is None:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_is_alive(record.process_id):
            return
        time.sleep(0.1)
    raise TimeoutError(
        f"CST session {record.session_id} acknowledged stop but process remained alive"
    )


def _process_is_alive(process_id: int) -> bool:
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, process_id
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            ):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def project_runtime_directory(project_directory: str | Path) -> Path:
    project_directory = Path(project_directory).resolve()
    config_path = project_directory / "project.ini"
    if config_path.is_file():
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")
        configured = config.get("DIRS", "tempdir", fallback="temp")
        path = Path(configured)
        return path.resolve() if path.is_absolute() else (project_directory / path).resolve()
    return project_directory / "temp"


def discover_managed_sessions(project_directory: str | Path) -> list[ManagedSessionRecord]:
    runtime = project_runtime_directory(project_directory)
    records = []
    if not runtime.is_dir():
        return records
    for worker_root in sorted(runtime.glob("worker_*")):
        if not worker_root.is_dir():
            continue
        for session_root in sorted(worker_root.iterdir()):
            protocol = session_root / "protocol"
            marker_path = session_root / "worker.state"
            if not session_root.is_dir() or not protocol.is_dir() or not marker_path.is_file():
                continue
            pid_path = session_root / "worker.pid"
            process_id = None
            process_alive = None
            if pid_path.is_file():
                try:
                    process_id = int(pid_path.read_text(encoding="ascii").strip())
                    process_alive = _process_is_alive(process_id)
                except (OSError, ValueError):
                    process_id = None
                    process_alive = None
            records.append(
                ManagedSessionRecord(
                    worker_id=worker_root.name.removeprefix("worker_"),
                    session_id=session_root.name,
                    root=session_root,
                    marker=marker_path.read_text(encoding="ascii", errors="replace").strip(),
                    has_completion=(protocol / "current.completion").is_file(),
                    has_ack=(protocol / "current.ack").is_file(),
                    has_stop_ack=(protocol / "stop.ack").is_file(),
                    process_id=process_id,
                    process_alive=process_alive,
                    recovery_disposition=_read_recovery_disposition(session_root),
                )
            )
    return records


def recover_project_sessions(
    project_directory: str | Path,
    *,
    timeout_per_session: float = 1200.0,
) -> list[ManagedSessionRecord]:
    records = [
        item for item in discover_managed_sessions(project_directory) if item.needs_recovery
    ]
    failures = []
    for item in records:
        if item.process_alive is False and not item.has_stop_ack:
            # Each worker operates on an isolated project copy. Once the recorded
            # process is definitively dead, the unfinished task can be abandoned
            # and replayed from the last atomic HOM checkpoint.
            _write_recovery_receipt(
                item,
                "abandoned-dead",
                completion=_read_completion(item),
            )
            (item.root / "worker.state").write_text(
                "abandoned-dead", encoding="ascii"
            )
            continue
        try:
            completion = recover_and_stop_session(
                item.root / "protocol",
                item.session_id,
                timeout=timeout_per_session,
            )
            _wait_for_process_exit(item, timeout_per_session)
            _write_recovery_receipt(item, "standard-stop", completion=completion)
        except Exception as exc:
            failures.append(f"{item.session_id}: {exc}")
    remaining = [
        item for item in discover_managed_sessions(project_directory) if item.needs_recovery
    ]
    if failures or remaining:
        sessions = ", ".join(item.session_id for item in remaining)
        details = "; ".join(failures)
        raise RuntimeError(
            "managed CST sessions still require recovery: "
            + (sessions or details)
            + (f"; failures: {details}" if sessions and details else "")
        )
    return records
