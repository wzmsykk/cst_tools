"""Application boundary between the Qt interface and the CST backend."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol, runtime_checkable

from csttool.application_backend import CstApplicationBackend


@dataclass(frozen=True)
class RunRequest:
    resume: bool
    worker_count: int

    def __post_init__(self):
        if self.worker_count < 1:
            raise ValueError("worker_count must be at least 1")


@runtime_checkable
class ApplicationBackend(Protocol):
    logger: logging.Logger
    supports_cst_backend_selection: bool

    def select_project_directory(self, path: str) -> None: ...

    def select_cst_file(self, path: str) -> None: ...

    def get_cst_installations(self): ...

    def get_selected_cst_installation(self): ...

    def select_cst_installation(self, version: int, executable: str): ...

    def get_postprocess_settings(self): ...

    def update_postprocess_settings(self, values) -> None: ...

    def get_algorithm_settings(self): ...

    def update_algorithm_settings(self, values) -> None: ...

    def initialize_run(self, resume: bool, worker_count: int) -> None: ...

    def prepare_run(self) -> None: ...

    def execute_run(self): ...

    def request_stop(self) -> None: ...

    def recover_project_sessions(self): ...

    def get_recovery_sessions(self): ...

    def is_recovery_required(self) -> bool: ...

    def add_progress_listener(self, listener) -> None: ...


class CstApplicationService:
    """Stable GUI facade backed by the production application backend."""

    def __init__(self, backend=None):
        candidate = backend or CstApplicationBackend()
        if not isinstance(candidate, ApplicationBackend):
            raise TypeError("backend does not implement ApplicationBackend")
        self._backend = candidate
        self.logger = self._backend.logger

    @property
    def backend(self):
        return self._backend

    def select_project_directory(self, path: str) -> None:
        self._backend.select_project_directory(path)

    def select_cst_file(self, path: str) -> None:
        self._backend.select_cst_file(path)

    @property
    def supports_cst_backend_selection(self) -> bool:
        return self._backend.supports_cst_backend_selection

    def get_cst_installations(self):
        return self._backend.get_cst_installations()

    def get_selected_cst_installation(self):
        return self._backend.get_selected_cst_installation()

    def select_cst_installation(self, version: int, executable: str):
        return self._backend.select_cst_installation(version, executable)

    def get_postprocess_settings(self):
        return self._backend.get_postprocess_settings()

    def update_postprocess_settings(self, values) -> None:
        self._backend.update_postprocess_settings(values)

    def get_algorithm_settings(self):
        return self._backend.get_algorithm_settings()

    def update_algorithm_settings(self, values) -> None:
        self._backend.update_algorithm_settings(values)

    def initialize_run(self, request: RunRequest) -> None:
        self._backend.initialize_run(
            request.resume,
            request.worker_count,
        )

    def prepare_run(self) -> None:
        self._backend.prepare_run()

    def execute_run(self):
        return self._backend.execute_run()

    def request_stop(self) -> None:
        self._backend.request_stop()

    def recover_project_sessions(self):
        return self._backend.recover_project_sessions()

    def get_recovery_sessions(self):
        return self._backend.get_recovery_sessions()

    def is_recovery_required(self) -> bool:
        return self._backend.is_recovery_required()

    def add_progress_listener(self, listener) -> None:
        self._backend.add_progress_listener(listener)
