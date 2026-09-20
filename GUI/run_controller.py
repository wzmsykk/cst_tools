"""Qt run-state controller with a composed backend worker."""

from __future__ import annotations

from enum import Enum, auto

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from GUI.application_service import GuiApplicationService, RunRequest
from csttool.hom_scan import ScanInterrupted


class RunState(Enum):
    IDLE = auto()
    READY = auto()
    RUNNING = auto()
    STOPPING = auto()
    RECOVERING = auto()
    RECOVERY_REQUIRED = auto()
    FAILED = auto()


class InvalidRunState(RuntimeError):
    """A controller transition was requested from an invalid state."""


class _BackendRunWorker(QObject):
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)
    interrupted = pyqtSignal()
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
        except ScanInterrupted:
            self.interrupted.emit()
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


class _BackendRecoveryWorker(QObject):
    succeeded = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, service: GuiApplicationService):
        super().__init__()
        self._service = service

    @pyqtSlot()
    def execute(self) -> None:
        try:
            recovered = self._service.recover_project_sessions()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(len(recovered))


class GuiRunController(QObject):
    state_changed = pyqtSignal(object)
    stage_changed = pyqtSignal(str)
    progress_changed = pyqtSignal(int, int)
    error = pyqtSignal(str)
    settled = pyqtSignal()
    cst_progress = pyqtSignal(object)

    _ALLOWED = {
        RunState.IDLE: frozenset(
            {RunState.READY, RunState.RECOVERING, RunState.RECOVERY_REQUIRED}
        ),
        RunState.READY: frozenset(
            {
                RunState.IDLE,
                RunState.RUNNING,
                RunState.RECOVERING,
                RunState.RECOVERY_REQUIRED,
            }
        ),
        RunState.RUNNING: frozenset(
            {
                RunState.IDLE,
                RunState.READY,
                RunState.STOPPING,
                RunState.RECOVERY_REQUIRED,
                RunState.FAILED,
            }
        ),
        RunState.STOPPING: frozenset(
            {
                RunState.IDLE,
                RunState.READY,
                RunState.RECOVERY_REQUIRED,
                RunState.FAILED,
            }
        ),
        RunState.RECOVERING: frozenset(
            {RunState.IDLE, RunState.READY, RunState.RECOVERY_REQUIRED}
        ),
        RunState.RECOVERY_REQUIRED: frozenset(
            {RunState.IDLE, RunState.READY, RunState.RECOVERING}
        ),
        RunState.FAILED: frozenset(
            {
                RunState.IDLE,
                RunState.READY,
                RunState.RUNNING,
                RunState.RECOVERING,
                RunState.RECOVERY_REQUIRED,
            }
        ),
    }

    def __init__(self, service: GuiApplicationService):
        super().__init__()
        self.service = service
        self.state = RunState.IDLE
        self.inputs_ready = False
        self.recovery_count = 0
        self._thread: QThread | None = None
        self._worker: _BackendRunWorker | None = None
        self._stop_thread: QThread | None = None
        self._stop_worker: _BackendStopWorker | None = None
        self._terminal_after_stop: RunState | None = None
        self._recovery_thread: QThread | None = None
        self._recovery_worker: _BackendRecoveryWorker | None = None
        self.service.add_progress_listener(self.cst_progress.emit)

    def set_inputs_ready(self, ready: bool) -> None:
        self.inputs_ready = bool(ready)
        if self.state in {
            RunState.RUNNING,
            RunState.STOPPING,
            RunState.RECOVERING,
            RunState.RECOVERY_REQUIRED,
        }:
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
        worker.interrupted.connect(self._run_interrupted)
        worker.stage_changed.connect(self._on_stage)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.interrupted.connect(thread.quit)
        worker.succeeded.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.interrupted.connect(worker.deleteLater)
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
            or self._recovery_thread is not None
        )

    def request_recovery(self) -> bool:
        if self.state not in {
            RunState.IDLE,
            RunState.READY,
            RunState.FAILED,
            RunState.RECOVERY_REQUIRED,
        }:
            return False
        if self._recovery_thread is not None or self._thread is not None:
            return False
        thread = QThread(self)
        worker = _BackendRecoveryWorker(self.service)
        worker.moveToThread(thread)
        thread.started.connect(worker.execute)
        worker.succeeded.connect(self._recovery_succeeded)
        worker.failed.connect(self._recovery_failed)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.succeeded.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._recovery_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._recovery_thread = thread
        self._recovery_worker = worker
        self._transition(RunState.RECOVERING)
        self._on_stage("recovering")
        thread.start()
        return True

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
            "recovering": 1,
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
        requires_recovery = self._backend_requires_recovery()
        target = (
            RunState.RECOVERY_REQUIRED if requires_recovery else RunState.FAILED
        )
        if self.state is RunState.STOPPING:
            self._terminal_after_stop = target
        else:
            self._transition(target)
        self.error.emit(message)

    def _run_interrupted(self) -> None:
        self._on_stage("interrupted")
        target = RunState.READY if self.inputs_ready else RunState.IDLE
        if self.state is RunState.STOPPING:
            self._terminal_after_stop = target
        else:
            self._transition(target)

    def _thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        self._emit_settled_if_idle()

    def _stop_failed(self, message: str) -> None:
        if self._backend_requires_recovery():
            self._terminal_after_stop = RunState.RECOVERY_REQUIRED
        self.error.emit(f"标准停止失败: {message}")

    def _stop_thread_finished(self) -> None:
        self._stop_worker = None
        self._stop_thread = None
        self._emit_settled_if_idle()

    def _recovery_succeeded(self, count: int) -> None:
        self.recovery_count = 0
        self._on_stage("recovered")
        self.service.logger.info("会话恢复完成：%d 个", count)
        self._transition(RunState.READY if self.inputs_ready else RunState.IDLE)

    def _recovery_failed(self, message: str) -> None:
        self._transition(RunState.RECOVERY_REQUIRED)
        self.error.emit(f"会话恢复失败: {message}")

    def inspect_recovery_state(self) -> int:
        if self.has_active_work:
            return self.recovery_count
        sessions = self.service.get_recovery_sessions()
        self.recovery_count = len(sessions)
        if self.recovery_count:
            self._transition(RunState.RECOVERY_REQUIRED)
        elif self.state is RunState.RECOVERY_REQUIRED:
            self._transition(RunState.READY if self.inputs_ready else RunState.IDLE)
        return self.recovery_count

    def mark_recovery_required(self, count: int = 0) -> None:
        self.recovery_count = max(0, int(count))
        if self.state is not RunState.RECOVERY_REQUIRED:
            self._transition(RunState.RECOVERY_REQUIRED)

    def _backend_requires_recovery(self) -> bool:
        try:
            required = self.service.is_recovery_required()
            if required:
                self.recovery_count = len(self.service.get_recovery_sessions())
            return required
        except Exception:
            self.service.logger.exception(
                "无法确认 CST 会话是否已安全关闭；按需要恢复处理"
            )
            return True

    def _recovery_thread_finished(self) -> None:
        self._recovery_worker = None
        self._recovery_thread = None
        self._emit_settled_if_idle()

    def _emit_settled_if_idle(self) -> None:
        if (
            self._thread is None
            and self._stop_thread is None
            and self._recovery_thread is None
        ):
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
