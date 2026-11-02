"""Discovery and protocol recovery for managed CST sessions in one project."""

from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from .managed_session_recovery import recover_and_stop_session
from .configuration import ProjectSettings, read_ini
from .runtime_protocol import atomic_publish, decode_completion, decode_task
from .session_closure import (collect_close_evidence, evaluate_closure,
                              read_recorded_exit)
from .process_identity import observe_process_identity
from .recovery_control import RecoveryPaused


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
    exit_code: int | None = None
    pending_result_task_id: str | None = None
    identity_reason: str = ''

    @property
    def closure(self):
        return evaluate_closure(collect_close_evidence(self.root, self.session_id, self.process_alive,
            self.exit_code,
            abandoned=self.recovery_disposition == 'abandoned-dead',
            unresolved_completion=self.has_completion and self.recovery_disposition is None,
            unresolved_result=self.pending_result_task_id is not None and self.recovery_disposition is None,
            result_state='received-unadopted' if self.pending_result_task_id is not None else 'unknown'))

    @property
    def needs_recovery(self) -> bool:
        return self.closure.needs_recovery


def _pending_result_task(session_root: Path) -> str | None:
    """ACK cleanup may have removed Completion before the algorithm adopted it."""
    context_path = session_root / 'task-context.json'
    if not context_path.exists():
        return None
    context = json.loads(context_path.read_text(encoding='utf-8'))
    task_id = context['task_id']
    path = Path(context.get('receipt_path', session_root / 'received' / (task_id + '.json')))
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    from .runtime_protocol import _validate_uuid
    _validate_uuid('pending result task_id', task_id)
    if (context.get('session_id') != session_root.name or value.get('session_id') != session_root.name
            or value.get('task_id') != task_id):
        raise ValueError('pending result receipt task/session identity mismatch')
    if value.get('phase') not in {'received', 'acknowledged', 'algorithm_adopted'}:
        raise ValueError('pending result receipt phase is invalid')
    if value.get('status') not in {'Success', 'Failure'}:
        raise ValueError('pending result receipt status is invalid')
    return task_id if (value.get('status') == 'Success'
                       and value['phase'] in {'received', 'acknowledged'}) else None


def _read_recovery_disposition(session_root: Path) -> str | None:
    receipt = session_root / 'recovery-l1.json'
    if not receipt.exists():
        receipt = session_root / "recovery.json"
    if not receipt.is_file():
        return None
    try:
        value = json.loads(receipt.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('session_id') != session_root.name
                or value.get('worker_id') != session_root.parent.name.removeprefix('worker_')):
            return None
        completion_path = session_root / 'protocol/current.completion'
        if completion_path.exists():
            completion = decode_completion(completion_path.read_text(encoding='utf-8'))
            if (completion.session_id != session_root.name
                    or completion.task_id != value.get('completion_task_id')):
                return None
        pending = _pending_result_task(session_root)
        if pending is not None and pending not in {value.get('received_task_id'), value.get('completion_task_id')}:
            return None
        disposition = value.get('disposition')
        return disposition if disposition in {'standard-stop', 'abandoned-dead'} else None
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
        "received_task_id": record.pending_result_task_id,
        "closure": asdict(record.closure),
        "completion_task_id": getattr(completion, "task_id", None),
        "completion_status": (
            getattr(getattr(completion, "status", None), "value", None)
        ),
    }
    target = record.root / 'recovery.json'
    if target.exists():
        # Never overwrite a historical recovery decision. A verified new
        # decision supersedes it with an explicitly named supplementary record.
        if _read_recovery_disposition(record.root) is None:
            raise ValueError('invalid historical recovery receipt; preserve evidence')
        target = record.root / 'recovery-l1.json'
    atomic_publish(target, json.dumps(document, ensure_ascii=False, indent=2))


def _read_completion(record: ManagedSessionRecord):
    path = record.root / "protocol" / "current.completion"
    if not path.is_file():
        return None
    try:
        completion = decode_completion(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return completion if completion.session_id == record.session_id else None


_UNREAD_EXIT = object()


def _owned_alive(root, pid, *, exit_code=_UNREAD_EXIT):
    state, reason = observe_process_identity(root, pid)
    # A verified durable exit proof is stronger than a newly reused numeric PID.
    if exit_code is _UNREAD_EXIT:
        exit_code = read_recorded_exit(root, Path(root).name, pid)
    if exit_code is not None:
        return False, '已核验历史退出及保存证据'
    if state == 'matched':
        return _process_tree_is_alive(pid), reason
    if state == 'absent':
        # Without a matching parent identity, raw parent-PID ancestry cannot
        # attribute orphan children safely. Require explicit verification.
        children = _windows_descendant_process_ids(pid)
        return (False if children == set() else None), reason
    if state == 'unknown' and not (Path(root) / 'process-identity.json').exists():
        # Absence can be observed without claiming ownership of a live PID.
        if _process_tree_is_alive(pid) is False:
            return False, '旧会话PID及子进程均已不存在'
    return None, reason


def _wait_for_process_exit(record: ManagedSessionRecord, timeout: float, *, pause_check=None) -> None:
    if record.process_id is None:
        raise RuntimeError('CST process identity is unknown; exit cannot be confirmed')
    deadline = time.monotonic() + timeout
    while True:
        if pause_check:
            pause_check()
        alive, reason = _owned_alive(record.root, record.process_id)
        if alive is False:
            return
        if alive is None:
            raise RuntimeError('CST process identity is unknown: ' + reason)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(.1, remaining))
    raise TimeoutError(
        f"CST session {record.session_id} acknowledged stop but process remained alive"
    )


def _process_is_alive(process_id: int) -> bool | None:
    import psutil
    if process_id <= 0:
        return None
    try:
        return psutil.Process(process_id).is_running()
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError):
        return None


def _windows_descendant_process_ids(process_id: int) -> set[int] | None:
    """Return descendants using parent PIDs retained by the Windows snapshot."""
    if os.name != "nt":
        return set()
    th32cs_snapprocess = 0x00000002
    invalid_handle_value = ctypes.c_void_p(-1).value

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if snapshot in (None, invalid_handle_value):
        return None
    parents: dict[int, set[int]] = {}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        success = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        if not success:
            return None
        while success:
            parents.setdefault(int(entry.th32ParentProcessID), set()).add(
                int(entry.th32ProcessID)
            )
            success = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        # ERROR_NO_MORE_FILES is the only successful snapshot termination.
        if kernel32.GetLastError() != 18:
            return None
    finally:
        kernel32.CloseHandle(snapshot)

    descendants = set()
    pending = list(parents.get(process_id, ()))
    while pending:
        child = pending.pop()
        if child in descendants:
            continue
        descendants.add(child)
        pending.extend(parents.get(child, ()))
    return descendants


def _process_tree_is_alive(process_id: int) -> bool | None:
    parent = _process_is_alive(process_id)
    if parent is True:
        return True
    descendants = _windows_descendant_process_ids(process_id)
    if descendants is None:
        return None
    states = [_process_is_alive(pid) for pid in descendants]
    if any(state is True for state in states):
        return True
    return None if parent is None or any(state is None for state in states) else False


def project_runtime_directory(project_directory: str | Path) -> Path:
    project_directory = Path(project_directory).resolve()
    config_path = project_directory / "project.ini"
    if config_path.is_file():
        settings = ProjectSettings.from_parser(read_ini(config_path))
        path = settings.directories.temp
        return path.resolve() if path.is_absolute() else (project_directory / path).resolve()
    return project_directory / "temp"


def discover_managed_sessions(project_directory: str | Path, *, progress=None, pause_check=None) -> list[ManagedSessionRecord]:
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
            if not session_root.is_dir() or not protocol.is_dir():
                continue
            if pause_check:
                pause_check()
            if progress:
                progress({'stage': 'session-discovery', 'session_id': session_root.name,
                          'reason': '核验进程身份、历史退出和协议证据'})
            records.append(_read_session(session_root))
    return records


def _read_session(session_root):
    protocol = session_root / 'protocol'
    marker_path = session_root / 'worker.state'
    pid_path = session_root / "worker.pid"
    process_id = None
    process_alive = None
    exit_code = None
    identity_reason = '缺少进程PID，需人工核实'
    if pid_path.is_file():
        try:
            process_id = int(pid_path.read_text(encoding="ascii").strip())
            exit_code = read_recorded_exit(session_root, session_root.name, process_id)
            process_alive, identity_reason = _owned_alive(session_root, process_id, exit_code=exit_code)
        except (OSError, ValueError):
            process_id = None
            process_alive = None
    try:
        marker = marker_path.read_text(encoding='ascii').strip()
    except (OSError, UnicodeError):
        marker = 'unknown'
    return ManagedSessionRecord(
        worker_id=session_root.parent.name.removeprefix("worker_"),
        session_id=session_root.name,
        root=session_root,
        marker=marker,
        has_completion=(protocol / "current.completion").is_file(),
        has_ack=(protocol / "current.ack").is_file(),
        has_stop_ack=(protocol / "stop.ack").is_file(),
        process_id=process_id,
        process_alive=process_alive,
        recovery_disposition=_read_recovery_disposition(session_root),
        exit_code=exit_code,
        pending_result_task_id=_pending_result_task(session_root),
        identity_reason=identity_reason,
    )


def _solver_call_active(root, project):
    """Explicit current-task call/return trace only; never infer from CPU usage."""
    try:
        if (root / 'protocol/current.completion').exists():
            return False
        with (root / 'protocol/current.task').open('rb') as stream:
            raw_task = stream.read(262145)
        if len(raw_task) > 262144:
            return False
        task = decode_task(raw_task.decode('utf-8'))
        context_path = root / 'task-context.json'
        with context_path.open('rb') as stream:
            raw_context = stream.read(1048577)
        if len(raw_context) > 1048576:
            return False
        context = json.loads(raw_context)
        if (task.session_id != root.name or context['session_id'] != root.name
                or task.task_id != context['task_id']):
            return False
        observation = Path(context.get('receipt_path', root / 'received/task.json')).parent.parent
        if not observation.resolve().is_relative_to(Path(project).resolve()) or observation.name != root.name:
            return False
        trace = observation / 'lifecycle.log'
        if trace.stat().st_mtime_ns < context_path.stat().st_mtime_ns:
            return False
        with trace.open('rb') as stream:
            stream.seek(max(0, trace.stat().st_size - 8192))
            lines = stream.read(8192).split(b'\n')[:-1]
        if not lines:
            return False
        expected = f'stage=solver-start; path={root / "worker-input.cst"}; calling EigenmodeSolver.Start'
        return lines[-1].decode('utf-8').strip().endswith(expected)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def recover_project_sessions(
    project_directory: str | Path,
    *,
    timeout_per_session: float = 1200.0,
    progress=None,
    pause_check=None,
) -> list[ManagedSessionRecord]:
    from .definition_sessions import recover_definition_sessions
    recover_definition_sessions(project_directory,timeout=min(timeout_per_session,60),progress=progress,pause_check=pause_check)
    if progress:
        progress({'stage': 'session-discovery', 'reason': '核验会话身份与收尾证据'})
    records = [
        item for item in (discover_managed_sessions(project_directory, progress=progress, pause_check=pause_check)
                         if progress or pause_check else discover_managed_sessions(project_directory)) if item.needs_recovery
    ]
    failures = []
    for item in records:
        try:
            if pause_check:
                pause_check()
            if progress:
                progress({'stage': 'session-recovery', 'session_id': item.session_id,
                          'reason': item.identity_reason})
            from .result_reconciliation import recover_completed_result
            deadline = time.monotonic() + timeout_per_session
            last_observed = time.monotonic()
            solver_was_active = False
            def wait_remaining():
                nonlocal deadline, last_observed, solver_was_active
                now = time.monotonic()
                if solver_was_active:
                    deadline += now - last_observed
                active = _solver_call_active(item.root, project_directory)
                if progress and active != solver_was_active:
                    progress({'stage': 'waiting-solver' if active else 'waiting-stop',
                              'session_id': item.session_id,
                              'reason': '已确认当前任务仍在Solver.Start内，求解不设总超时，可暂停恢复'
                                        if active else '等待通信及正常收尾（有界）'})
                solver_was_active = active
                last_observed = now
                return max(.001, deadline - now) if active else deadline - now
            if item.process_alive is None:
                raise RuntimeError('CST process identity/state is unknown; manual verification required: ' + item.identity_reason)
            closure = item.closure
            blocked = ('stop-ack-invalid', 'close-protocol-invalid')
            if item.process_alive is False:
                blocked += ('close-receipt-pending',)
            if any(reason.startswith(blocked) for reason in closure.missing_evidence):
                raise RuntimeError('invalid StopAck/close protocol; preserve protocol evidence')
            recover_completed_result(item.root)
            completion = _read_completion(item)
            if item.has_completion and completion is None:
                raise RuntimeError('invalid Completion; preserve protocol evidence')
            if item.process_alive is True:
                alive, reason = _owned_alive(item.root, item.process_id)
                if alive is None:
                    raise RuntimeError('CST ownership changed before recovery: ' + reason)
                if progress:
                    progress({'stage': 'waiting-stop', 'session_id': item.session_id,
                              'reason': '等待已确认归属的CST完成协议收尾并退出',
                              'timeout_seconds': max(0., deadline - time.monotonic())})
                def peer_exited():
                    alive, reason = _owned_alive(item.root, item.process_id)
                    if alive is None:
                        raise RuntimeError('CST process identity became unknown during recovery: ' + reason)
                    return alive is False
                completion = recover_and_stop_session(item.root / 'protocol', item.session_id,
                    timeout=max(0., deadline - time.monotonic()), peer_exited=peer_exited,
                    **({'progress': progress} if progress else {}),
                    **({'pause_check': pause_check} if pause_check else {}),
                    wait_remaining=wait_remaining)
                wait_remaining()
                if progress:
                    progress({'stage': 'waiting-stop', 'session_id': item.session_id,
                              'reason': '协议等待结束，核验CST进程退出',
                              'timeout_seconds': max(0., deadline - time.monotonic())})
                _wait_for_process_exit(item, max(0., deadline - time.monotonic()),
                                       **({'pause_check': pause_check} if pause_check else {}))
            recover_completed_result(item.root)
            # Re-observe after waiting. No return code is invented after losing
            # the original process handle: dead-but-unverified is abandonment.
            fresh = _read_session(item.root)
            if fresh.process_alive is not False:
                raise RuntimeError('CST exit is not confirmed')
            if any(reason.startswith(('stop-ack-invalid', 'close-protocol-invalid', 'close-receipt-pending'))
                   for reason in fresh.closure.missing_evidence):
                raise RuntimeError('invalid StopAck/close protocol after exit; preserve protocol evidence')
            disposition = 'standard-stop' if fresh.closure.standard_closed else 'abandoned-dead'
            _write_recovery_receipt(fresh, disposition, completion=completion)
            if disposition == 'abandoned-dead':
                (item.root / 'worker.state').write_text(disposition, encoding='ascii')
        except RecoveryPaused:
            raise
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
