"""Concurrent execution manager for local CST workers.

The manager owns a fixed-size worker pool.  Algorithms submit immutable tasks,
then execute a batch and collect results in submission order.  Worker creation
is injectable so the scheduler can be tested without starting CST.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
from pathlib import Path
from queue import Empty, Queue
from threading import RLock
from typing import Any, Callable, Iterable, Mapping, Protocol
import time


class WorkerProtocol(Protocol):
    """Worker operations required by the scheduler."""

    ID: str

    def runWithParam(self, resultname: str, *, params: Mapping[str, Any]) -> dict: ...

    def stop(self) -> Any: ...


class SimulationManager(Protocol):
    """Modern task API consumed by production algorithms."""

    currProjectDir: Path

    def getResultDir(self) -> Path: ...

    def execute(self, task: "SimulationTask") -> dict: ...

    def run_batch(self, tasks: Iterable["SimulationTask"]) -> list[dict]: ...

    def get_confirmed_snapshot(self) -> Path | None: ...

    def restore_project_snapshot(self, snapshot: str | Path) -> None: ...

    def stop(self) -> None: ...


class ManagerState(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOP_REQUESTED = auto()
    STOPPING = auto()
    CLOSED = auto()


class WorkerState(Enum):
    ALIVE = auto()
    RESTARTING = auto()
    DEAD = auto()


@dataclass(frozen=True, slots=True)
class SimulationTask:
    """One named CST simulation request."""

    params: Mapping[str, Any]
    job_name: str
    retry_count: int = 0
    continue_from_snapshot: bool = False

    def __post_init__(self) -> None:
        if not self.job_name:
            raise ValueError("job_name must not be empty")
        if self.retry_count < 0:
            raise ValueError("retry_count must be non-negative")


@dataclass(slots=True)
class _QueuedTask:
    sequence: int
    task: SimulationTask


@dataclass(slots=True)
class _WorkerSlot:
    worker_id: str
    worker: WorkerProtocol
    completed_jobs: int = 0
    state: WorkerState = WorkerState.ALIVE
    confirmed_snapshot: Path | None = None


WorkerFactory = Callable[[str, dict[str, Any], logging.Logger], WorkerProtocol]


class CSTManager:
    """Manage a bounded pool of replaceable local CST workers.

    Algorithms submit immutable tasks through :meth:`run_batch` or
    :meth:`execute`.
    """

    def __init__(
        self,
        gconfm,
        pconfm,
        params,
        logger: logging.Logger | None = None,
        maxTask: int = 2,
        *,
        worker_factory: WorkerFactory,
        max_jobs_per_worker: int = 10,
        progress_callback=None,
    ) -> None:
        if maxTask < 1:
            raise ValueError("maxTask must be at least 1")
        if max_jobs_per_worker < 1:
            raise ValueError("max_jobs_per_worker must be at least 1")

        self.logger = logger or logging.getLogger(__name__)
        self.pconfm = pconfm
        self.global_settings = gconfm.settings
        self.project_settings = pconfm.settings
        self.paramList = params
        self.maxParallelTasks = maxTask
        self.maxWorkerJobCountLimit = max_jobs_per_worker
        self._worker_factory = worker_factory
        self._progress_callback = progress_callback

        self.currProjectDir = Path(pconfm.currProjectDir).absolute()
        temp_path = self.project_settings.directories.temp
        result_path = self.project_settings.directories.result
        cst_filename = self.project_settings.cst_filename
        if cst_filename is None:
            raise ValueError("prepared project settings require a CST model filename")
        if self.global_settings.cst.executable is None:
            raise ValueError("global settings require a CST executable")
        self.tempDir = self._project_path(temp_path)
        self.resultDir = self._project_path(result_path)
        self.tempDir.mkdir(parents=True, exist_ok=True)
        self.resultDir.mkdir(parents=True, exist_ok=True)
        self.taskFileDir = self.tempDir
        self.cstProjPath = self.currProjectDir / cst_filename

        self._state = ManagerState.IDLE
        self._state_lock = RLock()
        self._task_queue: Queue[_QueuedTask] = Queue()
        self._result_queue: Queue[tuple[int, dict]] = Queue()
        self._slots: list[_WorkerSlot] = []
        self._next_sequence = 0
        self._confirmed_snapshot: Path | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=maxTask,
            thread_name_prefix="cst-worker",
        )
        self._start_initial_workers()
        self.logger.info(
            "MANAGER_READY project=%s workers=%d max_jobs_per_worker=%d",
            self.currProjectDir,
            self.maxParallelTasks,
            self.maxWorkerJobCountLimit,
        )

    def _project_path(self, configured_path: str) -> Path:
        path = Path(configured_path)
        return path if path.is_absolute() else self.currProjectDir / path

    @property
    def state(self) -> ManagerState:
        with self._state_lock:
            return self._state

    @property
    def ready(self) -> bool:
        return self.state is not ManagerState.CLOSED

    @property
    def stop_requested(self) -> bool:
        return self.state in {
            ManagerState.STOP_REQUESTED,
            ManagerState.STOPPING,
            ManagerState.CLOSED,
        }

    def _worker_config(
        self, worker_id: str, source_project: str | Path | None = None
    ) -> dict[str, Any]:
        worker_dir = self.tempDir / f"worker_{worker_id}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        return {
            "tempDir": str(worker_dir),
            "taskFileDir": str(worker_dir),
            "CSTENVPATH": str(self.global_settings.cst.executable),
            "resultDir": str(self.resultDir),
            "cstPath": str(source_project or self.cstProjPath),
            "paramList": self.paramList,
            "postProcess": self.pconfm.getCurrPPSList(),
            "runInBackground": True,
            "progressCallback": self._progress_callback,
        }

    def _create_worker(
        self, worker_id: str, source_project: str | Path | None = None
    ) -> WorkerProtocol:
        self.logger.debug("Creating CST worker %s", worker_id)
        return self._worker_factory(
            worker_id,
            self._worker_config(worker_id, source_project),
            self.logger,
        )

    def _start_initial_workers(self) -> None:
        for index in range(self.maxParallelTasks):
            worker_id = str(index)
            self._slots.append(_WorkerSlot(worker_id, self._create_worker(worker_id)))
            self.logger.info("WORKER_CREATED id=%s", worker_id)

    def getResultDir(self) -> Path:
        return self.resultDir

    def get_confirmed_snapshot(self) -> Path | None:
        """Return the newest task snapshot accepted by this manager."""
        with self._state_lock:
            return self._confirmed_snapshot

    @staticmethod
    def _validated_snapshot(snapshot: str | Path) -> Path:
        path = Path(snapshot).resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"confirmed CST snapshot is unavailable: {path}")
        return path

    def restore_project_snapshot(self, snapshot: str | Path) -> None:
        """Restart an idle pool from one previously confirmed project snapshot."""
        source = self._validated_snapshot(snapshot)
        with self._state_lock:
            if self._state is not ManagerState.IDLE:
                raise RuntimeError(
                    "CST snapshot can only be restored while manager is idle"
                )
            slots = list(self._slots)

        replacements: list[_WorkerSlot] = []
        try:
            for slot in slots:
                slot.worker.stop()
                slot.state = WorkerState.DEAD
            for slot in slots:
                worker = self._create_worker(slot.worker_id, source)
                replacements.append(
                    _WorkerSlot(
                        slot.worker_id,
                        worker,
                        confirmed_snapshot=source,
                    )
                )
        except Exception:
            for replacement in replacements:
                try:
                    replacement.worker.stop()
                except Exception:
                    self.logger.exception(
                        "Failed to stop partially restored CST worker %s",
                        replacement.worker_id,
                    )
            raise

        accepted = False
        with self._state_lock:
            if self._state is ManagerState.IDLE:
                self._slots = replacements
                self._confirmed_snapshot = source
                accepted = True
        if not accepted:
            for replacement in replacements:
                try:
                    replacement.worker.stop()
                finally:
                    replacement.state = WorkerState.DEAD
            raise RuntimeError("CST manager stopped while restoring project snapshot")
        self.logger.info("Restored CST worker pool from confirmed snapshot %s", source)

    def submit(self, task: SimulationTask) -> int:
        """Queue a task and return its monotonically increasing sequence ID."""
        with self._state_lock:
            if self._state in {
                ManagerState.STOP_REQUESTED,
                ManagerState.STOPPING,
                ManagerState.CLOSED,
            }:
                raise RuntimeError("CSTManager is shutting down or closed")
            sequence = self._next_sequence
            self._next_sequence += 1
            self._task_queue.put(_QueuedTask(sequence, task))
            self.logger.info(
                "TASK_QUEUED sequence=%d job=%s retries=%d continue_snapshot=%s",
                sequence,
                task.job_name,
                task.retry_count,
                task.continue_from_snapshot,
            )
            return sequence

    def _replace_worker(
        self, slot: _WorkerSlot, *, continue_from_snapshot: bool = False
    ) -> bool:
        slot.state = WorkerState.RESTARTING
        old_worker = slot.worker
        try:
            old_worker.stop()
        except Exception:
            self.logger.exception("Failed to stop CST worker %s", slot.worker_id)

        with self._state_lock:
            if self._state is not ManagerState.RUNNING:
                slot.state = WorkerState.DEAD
                return False

        try:
            # Snapshot continuation is opt-in. Standard batch tasks are
            # independent and must restart from the configured base project.
            source = slot.confirmed_snapshot if continue_from_snapshot else None
            if source is not None:
                try:
                    source = self._validated_snapshot(source)
                except FileNotFoundError:
                    self.logger.warning(
                        "Confirmed snapshot disappeared; falling back to base project: %s",
                        source,
                    )
                    source = None
                    slot.confirmed_snapshot = None
            slot.worker = self._create_worker(slot.worker_id, source)
        except Exception:
            slot.state = WorkerState.DEAD
            raise
        else:
            with self._state_lock:
                if self._state is not ManagerState.RUNNING:
                    try:
                        slot.worker.stop()
                    finally:
                        slot.state = WorkerState.DEAD
                    return False
            slot.completed_jobs = 0
            slot.state = WorkerState.ALIVE
            return True

    @staticmethod
    def _exception_result(task: SimulationTask, exc: Exception) -> dict[str, Any]:
        return {
            "TaskStatus": "Failure",
            "FailureReport": f"{type(exc).__name__}: {exc}",
            "RunName": task.job_name,
            "RunParameters": task.params,
            "PostProcessResult": None,
        }

    def _execute_task(self, slot: _WorkerSlot, task: SimulationTask) -> dict:
        result: dict[str, Any] | None = None
        started_at = time.monotonic()
        self.logger.info("TASK_START worker=%s job=%s", slot.worker_id, task.job_name)
        for attempt in range(task.retry_count + 1):
            try:
                result = slot.worker.runWithParam(
                    resultname=task.job_name,
                    params=task.params,
                )
            except Exception as exc:
                self.logger.exception(
                    "Worker %s raised while running %s",
                    slot.worker_id,
                    task.job_name,
                )
                result = self._exception_result(task, exc)

            if result.get("TaskStatus") != "Failure":
                snapshot_value = result.get("ProjectSnapshot")
                if snapshot_value and task.continue_from_snapshot:
                    snapshot = self._validated_snapshot(snapshot_value)
                    slot.confirmed_snapshot = snapshot
                    with self._state_lock:
                        self._confirmed_snapshot = snapshot
                slot.completed_jobs += 1
                self.logger.info(
                    "TASK_DONE worker=%s job=%s status=%s attempt=%d elapsed_seconds=%.3f",
                    slot.worker_id,
                    task.job_name,
                    result.get("TaskStatus", "Success"),
                    attempt + 1,
                    time.monotonic() - started_at,
                )
                return result

            self.logger.warning(
                "Worker %s failed task %s (attempt %d/%d); restarting",
                slot.worker_id,
                task.job_name,
                attempt + 1,
                task.retry_count + 1,
            )
            if self.stop_requested:
                break
            if not self._replace_worker(
                slot,
                continue_from_snapshot=task.continue_from_snapshot,
            ):
                break

        assert result is not None
        self.logger.error(
            "TASK_DONE worker=%s job=%s status=Failure attempts=%d elapsed_seconds=%.3f",
            slot.worker_id,
            task.job_name,
            task.retry_count + 1,
            time.monotonic() - started_at,
        )
        return result

    def _drain_tasks(self, slot: _WorkerSlot) -> None:
        while self.state is ManagerState.RUNNING:
            try:
                queued = self._task_queue.get_nowait()
            except Empty:
                return

            try:
                if slot.completed_jobs >= self.maxWorkerJobCountLimit:
                    self.logger.info(
                        "Worker %s reached the %d-job limit; restarting",
                        slot.worker_id,
                        self.maxWorkerJobCountLimit,
                    )
                    if not self._replace_worker(
                        slot,
                        continue_from_snapshot=queued.task.continue_from_snapshot,
                    ):
                        return
                result = self._execute_task(slot, queued.task)
                self._result_queue.put((queued.sequence, result))
            finally:
                self._task_queue.task_done()

    def _execute_queued_tasks(self) -> None:
        """Run every currently queued task and block until the batch finishes."""
        with self._state_lock:
            if self._state is ManagerState.CLOSED:
                raise RuntimeError("CSTManager is closed")
            if self._state is not ManagerState.IDLE:
                raise RuntimeError(f"CSTManager cannot start from {self._state.name}")
            if self._task_queue.empty():
                return
            self._state = ManagerState.RUNNING
            slots = [slot for slot in self._slots if slot.state is WorkerState.ALIVE]
            queued_count = self._task_queue.qsize()

        if not slots:
            with self._state_lock:
                self._state = ManagerState.IDLE
            raise RuntimeError("No live CST workers are available")

        futures: list[Future[None]] = []
        started_at = time.monotonic()
        self.logger.info(
            "BATCH_START tasks=%d live_workers=%d", queued_count, len(slots)
        )
        try:
            futures = [self._executor.submit(self._drain_tasks, slot) for slot in slots]
            for future in futures:
                future.result()
        finally:
            with self._state_lock:
                if self._state is ManagerState.RUNNING:
                    self._state = ManagerState.IDLE
            self.logger.info(
                "BATCH_DONE tasks=%d elapsed_seconds=%.3f state=%s",
                queued_count,
                time.monotonic() - started_at,
                self.state.name,
            )

    def _drain_results(self) -> list[tuple[int, dict]]:
        collected: list[tuple[int, dict]] = []
        while True:
            try:
                collected.append(self._result_queue.get_nowait())
            except Empty:
                break
        collected.sort(key=lambda item: item[0])
        return collected

    def run_batch(self, tasks: Iterable[SimulationTask]) -> list[dict]:
        for task in tasks:
            self.submit(task)
        self._execute_queued_tasks()
        return [result for _, result in self._drain_results()]

    def execute(self, task: SimulationTask) -> dict:
        results = self.run_batch([task])
        if not results:
            raise RuntimeError("CST task completed without a result")
        return results[0]

    def stop(self) -> None:
        with self._state_lock:
            if self._state is ManagerState.CLOSED:
                return
            self._state = ManagerState.STOPPING
            slots = list(self._slots)
        self.logger.info("MANAGER_STOP_START workers=%d", len(slots))

        def stop_slot(slot: _WorkerSlot):
            try:
                slot.worker.stop()
            except Exception as exc:
                self.logger.exception("Failed to stop CST worker %s", slot.worker_id)
                return exc
            finally:
                slot.state = WorkerState.DEAD
            return None

        with ThreadPoolExecutor(
            max_workers=len(slots) or 1,
            thread_name_prefix="cst-stop",
        ) as stop_executor:
            stop_errors = [
                error
                for error in stop_executor.map(stop_slot, slots)
                if error is not None
            ]

        self._executor.shutdown(wait=True, cancel_futures=True)
        self._clear_queue(self._task_queue)
        self._clear_queue(self._result_queue)
        with self._state_lock:
            self._slots.clear()
            self._state = ManagerState.CLOSED
        self.logger.info(
            "MANAGER_STOPPED workers=%d errors=%d", len(slots), len(stop_errors)
        )
        if stop_errors:
            raise RuntimeError(
                f"{len(stop_errors)} CST worker(s) did not stop cleanly"
            ) from stop_errors[0]

    def request_stop(self) -> None:
        """Stop dispatching new work without terminating the active solver."""
        with self._state_lock:
            if self._state in {
                ManagerState.STOP_REQUESTED,
                ManagerState.STOPPING,
                ManagerState.CLOSED,
            }:
                return
            self._state = ManagerState.STOP_REQUESTED
        self._clear_queue(self._task_queue)
        self.logger.info("CSTManager accepted cooperative stop request")

    def emergency_terminate(self) -> None:
        """Explicitly terminate live workers after standard shutdown failed."""
        with self._state_lock:
            slots = list(self._slots)
            self._state = ManagerState.STOPPING
        for slot in slots:
            terminate = getattr(slot.worker, "emergency_terminate", None)
            if terminate is None:
                raise RuntimeError(
                    f"worker {slot.worker_id} has no emergency termination API"
                )
            terminate()
            slot.state = WorkerState.DEAD
        self._executor.shutdown(wait=False, cancel_futures=True)
        with self._state_lock:
            self._slots.clear()
            self._state = ManagerState.CLOSED

    @staticmethod
    def _clear_queue(target: Queue) -> None:
        while True:
            try:
                target.get_nowait()
            except Empty:
                return
            else:
                target.task_done()

    def __enter__(self) -> "CSTManager":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()
