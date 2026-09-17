"""Application boundary between the Qt interface and the CST backend."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol

from csttool.application_backend import CstApplicationBackend


@dataclass(frozen=True)
class RunRequest:
    start_from_existing: bool
    safe_mode: bool
    worker_count: int

    def __post_init__(self):
        if self.worker_count < 1:
            raise ValueError("worker_count must be at least 1")


class GuiApplicationService(Protocol):
    logger: logging.Logger

    def select_project_directory(self, path: str) -> None: ...

    def select_cst_file(self, path: str) -> None: ...

    def get_postprocess_settings(self): ...

    def update_postprocess_settings(self, values) -> None: ...

    def get_algorithm_settings(self): ...

    def update_algorithm_settings(self, values) -> None: ...

    def initialize_run(self, request: RunRequest) -> None: ...

    def prepare_run(self) -> None: ...

    def execute_run(self): ...

    def request_stop(self) -> None: ...


class _LegacyBackendAdapter:
    """Temporary compatibility for injected old-style engines and test doubles."""

    def __init__(self, engine):
        self._engine = engine
        self.logger = self._engine.logger

    @property
    def engine(self):
        return self._engine

    def select_project_directory(self, path: str) -> None:
        self._engine.setProjectDir(path)

    def select_cst_file(self, path: str) -> None:
        self._engine.setCSTFilePath(path)

    def get_postprocess_settings(self):
        return self._engine.getCurrPostProcessList()

    def update_postprocess_settings(self, values) -> None:
        self._engine.setCurrPostProcessList(values)

    def get_algorithm_settings(self):
        return self._engine.getAlgAttrs()

    def update_algorithm_settings(self, values) -> None:
        self._engine.setAlgAttrs(values)

    def initialize_run(self, start_from_existing, safe_mode, worker_count) -> None:
        self._engine.setFlags(start_from_existing, safe_mode)
        self._engine.setWorkerCount(worker_count)
        if self._engine.wininit() is False:
            raise RuntimeError("CST 环境初始化失败")

    def prepare_run(self) -> None:
        if self._engine.setRunInfos() == 0:
            raise RuntimeError("运行配置准备失败")

    def execute_run(self):
        return self._engine.starttask()

    def request_stop(self) -> None:
        self._engine.request_stop()


class CstApplicationService:
    """Stable GUI facade backed by the production application backend."""

    def __init__(self, backend=None):
        candidate = backend or CstApplicationBackend()
        if not hasattr(candidate, "select_project_directory"):
            candidate = _LegacyBackendAdapter(candidate)
        self._backend = candidate
        self.logger = candidate.logger

    @property
    def backend(self):
        return self._backend

    def select_project_directory(self, path: str) -> None:
        self._backend.select_project_directory(path)

    def select_cst_file(self, path: str) -> None:
        self._backend.select_cst_file(path)

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
            request.start_from_existing,
            request.safe_mode,
            request.worker_count,
        )

    def prepare_run(self) -> None:
        self._backend.prepare_run()

    def execute_run(self):
        return self._backend.execute_run()

    def request_stop(self) -> None:
        self._backend.request_stop()
