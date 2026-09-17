"""Qt run-state controller with a composed backend worker."""

from __future__ import annotations

from enum import Enum, auto

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from GUI.application_service import GuiApplicationService, RunRequest


class RunState(Enum):
    IDLE = auto()
    READY = auto()
    RUNNING = auto()
    STOPPING = auto()
    FAILED = auto()


class InvalidRunState(RuntimeError):
    """A controller transition was requested from an invalid state."""


class _BackendRunWorker(QObject):
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)
    stage_changed = pyqtSignal(str)

    def __init__(
        self,
        service: GuiApplicationService,
        request: RunRequest,
    ):
        super().__init__()
        self._service = service
        self._request = request

    @pyqtSlot()
    def execute(self) -> None:
        try:
            self.stage_changed.emit("initializing")
            self._service.initialize_run(self._request)
            self.stage_changed.emit("preparing")
            self._service.prepare_run()
            self.stage_changed.emit("running")
            self._service.execute_run()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit()


class _BackendStopWorker(QObject):
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, service: GuiApplicationService):
        super().__init__()
        self._service = service

    @pyqtSlot()
    def execute(self) -> None:
        try:
            self._service.request_stop()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit()


class GuiRunController(QObject):
    state_changed = pyqtSignal(object)
    stage_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, int)
    error = pyqtSignal(str)
    settled = pyqtSignal()

    _ALLOWED = {
        RunState.IDLE: frozenset({RunState.READY}),
        RunState.READY: frozenset({RunState.IDLE, RunState.RUNNING}),
        RunState.RUNNING: frozenset(
            {RunState.IDLE, RunState.READY, RunState.STOPPING, RunState.FAILED}
        ),
        RunState.STOPPING: frozenset(
            {RunState.IDLE, RunState.READY, RunState.FAILED}
        ),
        RunState.FAILED: frozenset(
            {RunState.IDLE, RunState.READY, RunState.RUNNING}
        ),
    }

    def __init__(self, service: GuiApplicationService):
        super().__init__()
        self.service = service
        self.state = RunState.IDLE
        self.inputs_ready = False
        self._thread: QThread | None = None
        self._worker: _BackendRunWorker | None = None
        self._stop_thread: QThread | None = None
        self._stop_worker: _BackendStopWorker | None = None
        self._terminal_after_stop: RunState | None = None

    def set_inputs_ready(self, ready: bool) -> None:
        self.inputs_ready = bool(ready)
        if self.state in {RunState.RUNNING, RunState.STOPPING}:
            return
        target = RunState.READY if ready else RunState.IDLE
        if self.state is not target:
            self._transition(target)

    def start(
        self, start_from_existing: bool, safe: bool, worker_count: int = 2
    ) -> bool:
        if not self.inputs_ready:
            return False
        if self.state not in {RunState.READY, RunState.FAILED}:
            return False
        if self._thread is not None:
            return False

        thread = QThread(self)
        request = RunRequest(
            start_from_existing=bool(start_from_existing),
            safe_mode=bool(safe),
            worker_count=int(worker_count),
        )
        worker = _BackendRunWorker(self.service, request)
        worker.moveToThread(thread)
        thread.started.connect(worker.execute)
        worker.succeeded.connect(self._run_succeeded)
        worker.failed.connect(self._run_failed)
        worker.stage_changed.connect(self._on_stage)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.succeeded.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self._transition(RunState.RUNNING)
        thread.start()
        return True

    @property
    def has_active_work(self) -> bool:
        return (
            self.state in {RunState.RUNNING, RunState.STOPPING}
            or self._thread is not None
            or self._stop_thread is not None
        )

    def request_stop(self) -> bool:
        if self.state is RunState.STOPPING:
            return True
        if self.state is not RunState.RUNNING or self._stop_thread is not None:
            return False

        thread = QThread(self)
        worker = _BackendStopWorker(self.service)
        worker.moveToThread(thread)
        thread.started.connect(worker.execute)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(self._stop_failed)
        worker.failed.connect(thread.quit)
        worker.succeeded.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._stop_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._stop_thread = thread
        self._stop_worker = worker
        self._transition(RunState.STOPPING)
        self._on_stage("stopping")
        thread.start()
        return True

    def _on_stage(self, stage: str) -> None:
        progress = {
            "initializing": 1,
            "preparing": 2,
            "running": 3,
            "stopping": 3,
            "completed": 4,
        }.get(stage, 0)
        self.stage_changed.emit(stage)
        self.progress_changed.emit(progress, 4)

    def _run_succeeded(self) -> None:
        self._on_stage("completed")
        target = RunState.READY if self.inputs_ready else RunState.IDLE
        if self.state is RunState.STOPPING:
            self._terminal_after_stop = target
        else:
            self._transition(target)

    def _run_failed(self, message: str) -> None:
        if self.state is RunState.STOPPING:
            self._terminal_after_stop = RunState.FAILED
        else:
            self._transition(RunState.FAILED)
        self.error.emit(message)

    def _thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        self._emit_settled_if_idle()

    def _stop_failed(self, message: str) -> None:
        self.error.emit(f"标准停止失败: {message}")

    def _stop_thread_finished(self) -> None:
        self._stop_worker = None
        self._stop_thread = None
        self._emit_settled_if_idle()

    def _emit_settled_if_idle(self) -> None:
        if self._thread is None and self._stop_thread is None:
            if self.state is RunState.STOPPING:
                target = self._terminal_after_stop or (
                    RunState.READY if self.inputs_ready else RunState.IDLE
                )
                self._terminal_after_stop = None
                self._transition(target)
            self.settled.emit()

    def _transition(self, target: RunState) -> None:
        if target is self.state:
            return
        if target not in self._ALLOWED[self.state]:
            raise InvalidRunState(f"invalid GUI run-state transition: {self.state.name} -> {target.name}")
        self.state = target
        self.state_changed.emit(target)
