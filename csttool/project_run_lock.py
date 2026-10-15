"""Small cross-process lease preventing concurrent runs in one project."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
import json
import os
from pathlib import Path
import time
from uuid import uuid4
import socket
import psutil
from .runner_ownership import RunnerOwnership

from .project_session_recovery import project_runtime_directory


class ProjectRunBusyError(RuntimeError):
    """Another application instance currently owns the project."""


@dataclass(frozen=True, slots=True)
class ProjectRunOwner:
    process_id: int
    token: str
    acquired_at: str
    created_at: float | None = None
    host: str | None = None


def _process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            query_limited_information, False, process_id
        )
        if not handle:
            return ctypes.windll.kernel32.GetLastError() == 5
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


def _read_owner(path: Path) -> ProjectRunOwner | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return ProjectRunOwner(
            process_id=int(document["process_id"]),
            token=str(document["token"]),
            acquired_at=str(document["acquired_at"]),
            created_at=document.get('created_at'), host=document.get('host'),
        )
    except (KeyError, OSError, TypeError, ValueError):
        return None


def _is_recent(path: Path, seconds: float = 5.0) -> bool:
    try:
        return time.time() - path.stat().st_mtime < seconds
    except OSError:
        return False


class ProjectRunLock:
    """An atomic lock file whose ownership survives multiple GUI processes."""

    filename = ".cst-tools-run.lock"

    def __init__(self, project_directory: str | Path):
        runtime = project_runtime_directory(project_directory)
        self.path = runtime / self.filename
        self.owner = ProjectRunOwner(
            process_id=os.getpid(),
            token=str(uuid4()),
            acquired_at=datetime.now(timezone.utc).isoformat(),
            created_at=psutil.Process().create_time(), host=socket.gethostname(),
        )
        self.acquired = False

    def acquire(self) -> None:
        try:
            guard = RunnerOwnership(str(self.path) + '.guard').acquire()
        except RuntimeError as exc:
            raise ProjectRunBusyError('项目运行锁正在更新') from exc
        try:
            self._acquire_guarded()
        finally:
            guard.close()

    def _acquire_guarded(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "schema_version": 1,
                "process_id": self.owner.process_id,
                "token": self.owner.token,
                "acquired_at": self.owner.acquired_at,
                'created_at': self.owner.created_at, 'host': self.owner.host,
            },
            ensure_ascii=True,
        ).encode("utf-8")
        while True:
            try:
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                )
            except FileExistsError:
                existing = _read_owner(self.path)
                if existing is not None and _owner_is_alive(existing):
                    raise ProjectRunBusyError(
                        "该项目已在另一个窗口中运行"
                        f"（进程 {existing.process_id}，开始于 {existing.acquired_at}）"
                    )
                if existing is None:
                    raise ProjectRunBusyError("项目锁身份不可读，禁止自动抢占；请核实原运行归属")
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.acquired = True
            return

    def release(self) -> None:
        if not self.acquired:
            return
        guard = RunnerOwnership(str(self.path) + '.guard').acquire()
        try:
            self._release_guarded()
        finally:
            guard.close()

    def _release_guarded(self):
        existing = _read_owner(self.path)
        if existing is not None and existing.token == self.owner.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.acquired = False

    @classmethod
    def active_owner(cls, project_directory: str | Path) -> ProjectRunOwner | None:
        path = project_runtime_directory(project_directory) / cls.filename
        owner = _read_owner(path)
        if owner is None:
            if path.exists():
                return ProjectRunOwner(0, "unknown", "正在建立运行锁")
            return None
        if not _owner_is_alive(owner):
            return None
        return owner


def _owner_is_alive(owner):
    if owner.host and owner.host != socket.gethostname():
        return True  # Cross-host ownership cannot be established locally.
    if not _process_is_alive(owner.process_id):
        return False
    if owner.created_at is not None:
        try:
            return abs(psutil.Process(owner.process_id).create_time() - float(owner.created_at)) < .01
        except psutil.NoSuchProcess:
            return False
        except (psutil.AccessDenied, OSError, ValueError, TypeError):
            return True  # Unknown is not permission to steal the lease.
    return True
