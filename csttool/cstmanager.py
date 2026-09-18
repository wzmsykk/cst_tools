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
import warnings

from install_compat import resource_path

from . import cstworker


class WorkerProtocol(Protocol):
    """The part of ``local_cstworker`` used by the scheduler."""

    ID: str

    def runWithParam(self, resultname: str, *, params: Mapping[str, Any]) -> dict:
        ...

    def stop(self) -> Any:
        ...


class SimulationManager(Protocol):
    """Modern task API consumed by production algorithms."""

    currProjectDir: Path

    def getResultDir(self) -> Path: ...

    def execute(self, task: "SimulationTask") -> dict: ...

    def run_batch(self, tasks: Iterable["SimulationTask"]) -> list[dict]: ...

    def stop(self) -> None: ...


class ManagerState(Enum):
    IDLE = auto()
    RUNNING = auto()
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


WorkerFactory = Callable[[str, dict[str, Any], logging.Logger], WorkerProtocol]


class CSTManager:
    """Manage a bounded pool of replaceable local CST workers.

    ``startProcessing`` remains blocking for compatibility with the existing
    optimization algorithms.  New code can use :meth:`run_batch` or
    :meth:`execute` instead.
    """

    def __init__(
        self,
        gconfm,
        pconfm,
        params,
        logger: logging.Logger | None = None,
        maxTask: int = 2,
        *,
        worker_factory: WorkerFactory | None = None,
        max_jobs_per_worker: int = 10,
    ) -> None:
        if maxTask < 1:
            raise ValueError("maxTask must be at least 1")
        if max_jobs_per_worker < 1:
            raise ValueError("max_jobs_per_worker must be at least 1")

        self.logger = logger or logging.getLogger(__name__)
        self.pconfm = pconfm
        self.gconf = gconfm.conf
        self.pconf = pconfm.conf
        self.paramList = params
        self.maxParallelTasks = maxTask
        self.maxWorkerJobCountLimit = max_jobs_per_worker
        self._worker_factory = worker_factory or self._create_local_worker

        self.cstPatternDir = Path(resource_path(self.gconf["BASE"]["datadir"]))
        self.currProjectDir = Path(pconfm.currProjectDir).absolute()
        self.tempDir = self._project_path(self.pconf["DIRS"]["tempdir"])
        self.resultDir = self._project_path(self.pconf["DIRS"]["resultdir"])
        self.tempDir.mkdir(parents=True, exist_ok=True)
        self.resultDir.mkdir(parents=True, exist_ok=True)
        self.taskFileDir = self.tempDir
        self.cstProjPath = self.currProjectDir / self.pconf["CST"]["CSTFilename"]
        self.cstType = self.pconf["PROJECT"]["ProjectType"]

        self._state = ManagerState.IDLE
        self._state_lock = RLock()
        self._task_queue: Queue[_QueuedTask] = Queue()
        self._result_queue: Queue[tuple[int, dict]] = Queue()
        self._slots: list[_WorkerSlot] = []
        self._next_sequence = 0
        self._executor = ThreadPoolExecutor(
            max_workers=maxTask,
            thread_name_prefix="cst-worker",
        )
        self._start_initial_workers()

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
    def cstWorkerList(self) -> list[WorkerProtocol]:
        """Compatibility view of the live workers."""
        with self._state_lock:
            return [slot.worker for slot in self._slots]

    @property
    def cstWorkerStatus(self) -> list[str]:
        """Compatibility view of worker states."""
        with self._state_lock:
            return [slot.state.name for slot in self._slots]

    def _worker_config(self, worker_id: str) -> dict[str, Any]:
        worker_dir = self.tempDir / f"worker_{worker_id}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        return {
            "tempDir": str(worker_dir),
            "taskFileDir": str(worker_dir),
            "CSTENVPATH": self.gconf["CST"]["cstexepath"],
            "ProjectType": self.cstType,
            "cstPatternDir": str(self.cstPatternDir),
            "resultDir": str(self.resultDir),
            "cstPath": str(self.cstProjPath),
            "paramList": self.paramList,
            "postProcess": self.pconfm.getCurrPPSList(),
        }

    @staticmethod
    def _create_local_worker(
        worker_id: str,
        config: dict[str, Any],
        logger: logging.Logger,
    ) -> WorkerProtocol:
        return cstworker.local_cstworker(
            id=worker_id,
            type="local",
            workerconfig=config,
            logger=logger,
        )

    def _create_worker(self, worker_id: str) -> WorkerProtocol:
        self.logger.debug("Creating CST worker %s", worker_id)
        return self._worker_factory(
            worker_id,
            self._worker_config(worker_id),
            self.logger,
        )

    def _start_initial_workers(self) -> None:
        for index in range(self.maxParallelTasks):
            worker_id = str(index)
            self._slots.append(_WorkerSlot(worker_id, self._create_worker(worker_id)))
            self.logger.info("Created cstworker. ID=%s", worker_id)

    def getResultDir(self) -> Path:
        return self.resultDir

    def submit(self, task: SimulationTask) -> int:
        """Queue a task and return its monotonically increasing sequence ID."""
        with self._state_lock:
            if self._state in {ManagerState.STOPPING, ManagerState.CLOSED}:
                raise RuntimeError("CSTManager is shutting down or closed")
            sequence = self._next_sequence
            self._next_sequence += 1
            self._task_queue.put(_QueuedTask(sequence, task))
            return sequence

    def addTask(self, params: Mapping[str, Any], job_name: str, retry_cnt: int = 0) -> int:
        """Compatibility wrapper around :meth:`submit`."""
        # A historical caller used addTask(input_names, params, job_name).
        if not isinstance(job_name, str) and isinstance(retry_cnt, str):
            warnings.warn(
                "addTask(input_names, params, job_name) is deprecated; "
                "use addTask(params, job_name)",
                DeprecationWarning,
                stacklevel=2,
            )
            params, job_name, retry_cnt = job_name, retry_cnt, 0
        return self.submit(
            SimulationTask(params=params, job_name=job_name, retry_count=retry_cnt)
        )

    def _replace_worker(self, slot: _WorkerSlot) -> None:
        slot.state = WorkerState.RESTARTING
        old_worker = slot.worker
        try:
            old_worker.stop()
        except Exception:
            self.logger.exception("Failed to stop CST worker %s", slot.worker_id)

        try:
            slot.worker = self._create_worker(slot.worker_id)
        except Exception:
            slot.state = WorkerState.DEAD
            raise
        else:
            slot.completed_jobs = 0
            slot.state = WorkerState.ALIVE

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
                slot.completed_jobs += 1
                return result

            self.logger.warning(
                "Worker %s failed task %s (attempt %d/%d); restarting",
                slot.worker_id,
                task.job_name,
                attempt + 1,
                task.retry_count + 1,
            )
            self._replace_worker(slot)

        assert result is not None
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
                    self._replace_worker(slot)
                result = self._execute_task(slot, queued.task)
                self._result_queue.put((queued.sequence, result))
            finally:
                self._task_queue.task_done()

    def startProcessing(self) -> None:
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

        if not slots:
            with self._state_lock:
                self._state = ManagerState.IDLE
            raise RuntimeError("No live CST workers are available")

        futures: list[Future[None]] = []
        try:
            futures = [self._executor.submit(self._drain_tasks, slot) for slot in slots]
            for future in futures:
                future.result()
        finally:
            with self._state_lock:
                if self._state is ManagerState.RUNNING:
                    self._state = ManagerState.IDLE

    def synchronize(self) -> None:
        """Compatibility no-op: ``startProcessing`` is already blocking."""
        self._task_queue.join()

    def _drain_results(self) -> list[tuple[int, dict]]:
        collected: list[tuple[int, dict]] = []
        while True:
            try:
                collected.append(self._result_queue.get_nowait())
            except Empty:
                break
        collected.sort(key=lambda item: item[0])
        return collected

    def getFullResults(self) -> list[dict]:
        return [result for _, result in self._drain_results()]

    def getFirstResult(self) -> dict:
        collected = self._drain_results()
        if not collected:
            raise Empty("No CST results are available")
        first, *remaining = collected
        # Preserve any additional results for callers mixing the old APIs.
        for item in remaining:
            self._result_queue.put(item)
        return first[1]

    def run_batch(self, tasks: Iterable[SimulationTask]) -> list[dict]:
        for task in tasks:
            self.submit(task)
        self.startProcessing()
        return self.getFullResults()

    def execute(self, task: SimulationTask) -> dict:
        results = self.run_batch([task])
        if not results:
            raise RuntimeError("CST task completed without a result")
        return results[0]

    def runWithParam(
        self,
        params: Mapping[str, Any],
        job_name: str,
        retry_cnt: int = 0,
    ) -> dict:
        return self.execute(
            SimulationTask(params=params, job_name=job_name, retry_count=retry_cnt)
        )

    def runWithx(self, x: Mapping[str, Any], job_name: str) -> dict:
        warnings.warn(
            "runWithx is deprecated; use runWithParam",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.runWithParam(params=x, job_name=job_name)

    def stop(self) -> None:
        with self._state_lock:
            if self._state is ManagerState.CLOSED:
                return
            self._state = ManagerState.STOPPING
            slots = list(self._slots)

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
        self.logger.info("CSTManager stopped")
        if stop_errors:
            raise RuntimeError(
                f"{len(stop_errors)} CST worker(s) did not stop cleanly"
            ) from stop_errors[0]

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


# Backward-compatible name used throughout the existing application.
manager = CSTManager
