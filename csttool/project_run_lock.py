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

from .project_session_recovery import project_runtime_directory


class ProjectRunBusyError(RuntimeError):
    """Another application instance currently owns the project."""


@dataclass(frozen=True, slots=True)
class ProjectRunOwner:
    process_id: int
    token: str
    acquired_at: str


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


def _read_owner(path: Path) -> ProjectRunOwner | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        return ProjectRunOwner(
            process_id=int(document["process_id"]),
            token=str(document["token"]),
            acquired_at=str(document["acquired_at"]),
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
        )
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "schema_version": 1,
                "process_id": self.owner.process_id,
                "token": self.owner.token,
                "acquired_at": self.owner.acquired_at,
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
                if existing is not None and _process_is_alive(existing.process_id):
                    raise ProjectRunBusyError(
                        "该项目已在另一个窗口中运行"
                        f"（进程 {existing.process_id}，开始于 {existing.acquired_at}）"
                    )
                if existing is None and _is_recent(self.path):
                    raise ProjectRunBusyError("该项目正在被另一个窗口占用")
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
            if _is_recent(path):
                return ProjectRunOwner(0, "unknown", "正在建立运行锁")
            return None
        if not _process_is_alive(owner.process_id):
            return None
        return owner
