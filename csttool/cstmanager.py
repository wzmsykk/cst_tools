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
from uuid import uuid4

from .configuration import GlobalSettings, ProjectSettings
from .logging_config import ContextLogger
from .worker_models import WorkerConfig, SimulationResult
from .run_store import RunStore, logical_job_id
from .run_overview import RunOverview
from .result_reconciliation import execution_fingerprint, find_received_result
from .configuration import read_json, write_json_atomic
from .resource_admission import ResourceAdmission, ResourceBudget, ResourceAdmissionError


class WorkerProtocol(Protocol):
    """Worker operations required by the scheduler."""

    ID: str

    def run_task(self, result_name: str, *, params: Mapping[str, Any]) -> SimulationResult | dict: ...

    def stop(self) -> Any: ...


class SimulationManager(Protocol):
    """Modern task API consumed by production algorithms."""

    currProjectDir: Path

    @property
    def result_directory(self) -> Path: ...

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
    DRAINING = auto()
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


WorkerFactory = Callable[[str, WorkerConfig, logging.Logger], WorkerProtocol]


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
        max_jobs_per_worker: int = 6,
        progress_callback=None,
        run_id: str | None = None,
        run_directory: str | Path | None = None,
        run_overview: RunOverview | None = None,
        resource_budget: ResourceBudget | None = None,
        field_reference_result: Path | None = None,
        field_match_policy: Mapping[str, Any] | None = None,
        vacuum_domain: Mapping[str, Any] | None = None,
        stop_check=None,
    ) -> None:
        if maxTask < 1:
            raise ValueError("maxTask must be at least 1")
        if max_jobs_per_worker < 1:
            raise ValueError("max_jobs_per_worker must be at least 1")
        if vacuum_domain is not None and maxTask != 1:
            raise ValueError('optional vacuum domain registration requires one Worker')

        self.logger = logger or logging.getLogger(__name__)
        self._external_stop_check = stop_check or (lambda: False)
        self.pconfm = pconfm
        self.global_settings = gconfm.settings
        self.project_settings = pconfm.settings
        if not isinstance(self.global_settings, GlobalSettings):
            raise TypeError("global configuration requires GlobalSettings")
        if not isinstance(self.project_settings, ProjectSettings):
            raise TypeError("project configuration requires prepared ProjectSettings")
        self.paramList = params
        self.maxParallelTasks = maxTask
        self.maxWorkerJobCountLimit = max_jobs_per_worker
        self._worker_factory = worker_factory
        self._progress_callback = progress_callback
        self._field_reference_result = field_reference_result
        self._field_match_policy = field_match_policy
        self._vacuum_domain = None
        if vacuum_domain is not None:
            from .vacuum_domain_registry import validate_managed_domain_options
            self._vacuum_domain = validate_managed_domain_options(vacuum_domain)

        self.currProjectDir = Path(pconfm.currProjectDir).absolute()
        bound_run = getattr(self.logger, 'extra', {}).get('run_id')
        if run_id and bound_run and run_id != bound_run:
            raise ValueError('run_id does not match logger context')
        identity = run_id or bound_run or uuid4().hex
        if not isinstance(self.logger, ContextLogger) or not bound_run:
            self.logger = ContextLogger(self.logger, {
                "run_id": identity, "project": self.currProjectDir,
            })
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
        self._standalone_overview = None
        if run_directory is None:
            self._standalone_overview = RunOverview(self.currProjectDir, identity, '批量任务')
            run_directory = self._standalone_overview.directory
        self.run_store = RunStore(self.currProjectDir, run_directory, run_id=identity)
        self.run_store.overview = run_overview or self._standalone_overview
        self.execution_fingerprint = (execution_fingerprint(self.cstProjPath, {
            'postprocess': self.pconfm.get_postprocess_settings(),
            'cst_version': self.global_settings.cst.version,
            'executable': str(self.global_settings.cst.executable),
            **({'vacuum_domain':self._vacuum_domain} if self._vacuum_domain is not None else {}),
        })
                                      if self.cstProjPath.is_file() else None)
        self._received_paths = {}
        self.resource_admission = ResourceAdmission(resource_budget or ResourceBudget())
        self.resource_admission.check(maxTask)
        if self._vacuum_domain is not None:
            from .vacuum_domain_registry import register_vacuum_domain
            from .field_artifacts import SamplingSpec
            preflight = register_vacuum_domain(self.global_settings.cst.executable,self.cstProjPath,
                self.run_store.directory/'vacuum-preflight',
                SamplingSpec.from_mapping(self._vacuum_domain['sampling']),
                geometry_id=self._vacuum_domain['geometry_id'])
            if preflight['status'] != 'registered':
                raise ValueError('vacuum preflight rejected: '+','.join(preflight['rejection_reasons']))

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
            "Manager 已就绪 | MANAGER_READY project=%s workers=%d max_jobs_per_worker=%d",
            self.currProjectDir,
            self.maxParallelTasks,
            self.maxWorkerJobCountLimit, extra={"event": "MANAGER_READY", "phase": "lifecycle", "project": self.currProjectDir, "workers": self.maxParallelTasks, "max_jobs_per_worker": self.maxWorkerJobCountLimit})

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
        return getattr(self, '_external_stop_check', lambda: False)() or self.state in {
            ManagerState.STOP_REQUESTED,
            ManagerState.STOPPING,
            ManagerState.CLOSED,
        }

    def _worker_config(
        self, worker_id: str, source_project: str | Path | None = None
    ) -> WorkerConfig:
        worker_dir = self.tempDir / f"worker_{worker_id}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        postprocess = list(self.pconfm.get_postprocess_settings())
        if self._vacuum_domain is not None:
            for mode in self._vacuum_domain['modes']:
                params = {'iModeNumber':mode,'field_kind':'E','sampling':self._vacuum_domain['sampling']}
                if not any(item.get('method')=='ExportModeField' and item.get('params')==params
                           for item in postprocess):
                    postprocess.append({'method':'ExportModeField','resultName':f'vacuum_E_{mode}','params':params})
        return WorkerConfig(
            task_directory=worker_dir,
            result_directory=self.resultDir,
            executable=self.global_settings.cst.executable,
            project_path=Path(source_project or self.cstProjPath),
            parameters=tuple(self.paramList),
            postprocess=tuple(postprocess),
            progress_callback=self._progress_callback,
            run_directory=self.run_store.directory,
            project_directory=self.currProjectDir,
            execution_fingerprint=self.execution_fingerprint,
            field_reference_result=self._field_reference_result,
            field_match_policy=self._field_match_policy,
            vacuum_domain=self._vacuum_domain,
            vacuum_reference_store=self.run_store.directory/'vacuum-reference.json',
        )

    def _create_worker(
        self, worker_id: str, source_project: str | Path | None = None
    ) -> WorkerProtocol:
        self.logger.debug("创建 Worker | worker=%s project=%s", worker_id, self.currProjectDir)
        return self._worker_factory(
            worker_id,
            self._worker_config(worker_id, source_project),
            self.logger,
        )

    def _start_initial_workers(self) -> None:
        try:
            for index in range(self.maxParallelTasks):
                if self._external_stop_check():
                    self.request_stop()
                    break
                worker_id = str(index)
                self._slots.append(_WorkerSlot(worker_id, self._create_worker(worker_id)))
                if self._external_stop_check():
                    self.request_stop()
                    break
                self.logger.debug("Worker 已创建 | WORKER_CREATED worker=%s project=%s", worker_id, self.currProjectDir, extra={"event": "WORKER_CREATED", "phase": "lifecycle", "worker": worker_id, "project": self.currProjectDir})
        except Exception:
            self.stop()
            raise

    @property
    def result_directory(self) -> Path:
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
        self.logger.info("Worker 池已恢复 | project=%s snapshot=%s", self.currProjectDir, source)

    def submit(self, task: SimulationTask) -> int:
        """Queue a task and return its monotonically increasing sequence ID."""
        with self._state_lock:
            if getattr(self, '_external_stop_check', lambda: False)():
                raise RuntimeError('CSTManager stop intent is set')
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
                "任务已入队 | TASK_QUEUED sequence=%d job=%s retries=%d continue_snapshot=%s",
                sequence,
                task.job_name,
                task.retry_count,
                task.continue_from_snapshot, extra={"event": "TASK_QUEUED", "phase": "solve", "sequence": sequence, "job": task.job_name, "retries": task.retry_count, "continue_snapshot": task.continue_from_snapshot})
            return sequence

    def _replace_worker(
        self, slot: _WorkerSlot, *, continue_from_snapshot: bool = False
    ) -> bool:
        slot.state = WorkerState.DRAINING
        self.logger.info("Worker 重建开始 | WORKER_RESTART_START worker=%s continue_snapshot=%s", slot.worker_id, continue_from_snapshot, extra={"event": "WORKER_RESTART_START", "phase": "restart", "worker": slot.worker_id, "continue_snapshot": continue_from_snapshot})
        old_worker = slot.worker
        try:
            old_worker.stop()
        except Exception:
            self.logger.exception("Worker 关闭失败 | worker=%s project=%s", slot.worker_id, self.currProjectDir)
            slot.state = WorkerState.DEAD
            self.request_stop()
            raise RuntimeError('worker drain failed; replacement is forbidden until session recovery')

        slot.state = WorkerState.RESTARTING

        with self._state_lock:
            if self._state is not ManagerState.RUNNING:
                slot.state = WorkerState.DEAD
                self.logger.info("Worker 重建取消 | WORKER_RESTART_CANCELLED worker=%s reason=stop_requested", slot.worker_id, extra={"event": "WORKER_RESTART_CANCELLED", "phase": "restart", "worker": slot.worker_id})
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
            self.logger.exception("Worker 重建失败 | WORKER_RESTART_FAILED worker=%s", slot.worker_id, extra={"event": "WORKER_RESTART_FAILED", "phase": "restart", "worker": slot.worker_id})
            raise
        else:
            with self._state_lock:
                if self._state is not ManagerState.RUNNING:
                    try:
                        slot.worker.stop()
                    finally:
                        slot.state = WorkerState.DEAD
                        self.logger.info("Worker 重建后已停止 | WORKER_RESTART_CANCELLED worker=%s reason=stop_requested", slot.worker_id, extra={"event": "WORKER_RESTART_CANCELLED", "phase": "restart", "worker": slot.worker_id})
                    return False
            slot.completed_jobs = 0
            slot.state = WorkerState.ALIVE
            self.logger.info("Worker 重建完成 | WORKER_RESTART_DONE worker=%s source=%s", slot.worker_id, source or self.cstProjPath, extra={"event": "WORKER_RESTART_DONE", "phase": "restart", "worker": slot.worker_id, "source": source or self.cstProjPath})
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
        if task.continue_from_snapshot and self.execution_fingerprint:
            candidate = find_received_result([self.tempDir, self.currProjectDir / 'logs'],
                                              task.job_name, task.params, self.execution_fingerprint)
            if candidate:
                receipt_path, receipt = candidate
                if receipt.get('optional_analysis_pending'):
                    raise RuntimeError('completed solve has unfinished optional field analysis; recover analysis without replaying Solver')
                slot.confirmed_snapshot = self._validated_snapshot(receipt['snapshot'])
                if not self._replace_worker(slot, continue_from_snapshot=True):
                    raise RuntimeError('reconciled snapshot could not restore worker')
                self._confirmed_snapshot = slot.confirmed_snapshot
                self._received_paths[receipt['task_id']] = receipt_path
                self.run_store.event(receipt['task_id'], 'reconciled', job=task.job_name,
                                     parameters=dict(task.params))
                self.run_store.artifacts(receipt['task_id'], received=receipt_path,
                                         snapshot=Path(receipt['snapshot']))
                return {'TaskStatus': 'Success', 'RunName': task.job_name,
                        'RunParameters': dict(task.params), 'TaskID': receipt['task_id'],
                        'PostProcessResult': receipt['postprocess'], 'ReceiptPath': str(receipt_path),
                        'ProjectSnapshot': receipt['snapshot'],
                        'FieldArtifacts': receipt.get('field_artifacts'),
                        'FieldDiagnostic': receipt.get('field_diagnostic'),
                        'DomainRegistration': receipt.get('domain_registration'),
                        'ResultDirectory': receipt.get('result_directory', str(Path(receipt['snapshot']).parent))}
        result: dict[str, Any] | None = None
        started_at = time.monotonic()
        self.logger.info("任务开始 | TASK_START worker=%s job=%s project=%s", slot.worker_id, task.job_name, self.currProjectDir, extra={"event": "TASK_START", "phase": "solve", "worker": slot.worker_id, "job": task.job_name, "project": self.currProjectDir})
        for attempt in range(task.retry_count + 1):
            try:
                setter = getattr(slot.worker, 'set_attempt_context', None)
                if setter is not None:
                    setter(logical_job_id(task.job_name, task.params, self.execution_fingerprint), attempt + 1)
                with self.resource_admission.reservation():
                    result = slot.worker.run_task(
                        task.job_name,
                        params=task.params,
                    )
                if isinstance(result, SimulationResult):
                    result = result.to_mapping()
            except Exception as exc:
                self.logger.exception(
                    "Worker 执行异常 | worker=%s job=%s project=%s attempt=%d",
                    slot.worker_id,
                    task.job_name,
                    self.currProjectDir,
                    attempt + 1,
                )
                result = self._exception_result(task, exc)
                if isinstance(exc, ResourceAdmissionError):
                    self.request_stop()
                if getattr(exc, 'completed_result_pending', False):
                    result['AcknowledgmentPending'] = True
                    result['ReceiptPath'] = str(exc.receipt_path)
                    self.request_stop()  # Never automatically replay a completed solve.

            if result.get("TaskStatus") != "Failure":
                if result.get('TaskID') and result.get('ReceiptPath'):
                    self._received_paths[result['TaskID']] = Path(result['ReceiptPath'])
                snapshot_value = result.get("ProjectSnapshot")
                if snapshot_value and task.continue_from_snapshot:
                    snapshot = self._validated_snapshot(snapshot_value)
                    slot.confirmed_snapshot = snapshot
                    with self._state_lock:
                        self._confirmed_snapshot = snapshot
                slot.completed_jobs += 1
                self.logger.info(
                    "任务结束 | TASK_DONE worker=%s job=%s status=%s attempt=%d elapsed_seconds=%.3f",
                    slot.worker_id,
                    task.job_name,
                    result.get("TaskStatus", "Success"),
                    attempt + 1,
                    time.monotonic() - started_at, extra={"event": "TASK_DONE", "phase": "solve", "worker": slot.worker_id, "job": task.job_name, "status": result.get("TaskStatus", "Success"), "attempt": attempt + 1, "elapsed_seconds": time.monotonic() - started_at})
                return result

            self.logger.warning(
                "任务失败，准备检查停止状态并重建 Worker | worker=%s job=%s attempt=%d max_attempts=%d reason=%s",
                slot.worker_id,
                task.job_name,
                attempt + 1,
                task.retry_count + 1,
                result.get("FailureReport", "未提供失败原因"),
            )
            if self.stop_requested:
                break
            if not self._replace_worker(
                slot,
                continue_from_snapshot=task.continue_from_snapshot,
            ):
                break

        assert result is not None
        self.logger.error("任务已放弃 | TASK_ABANDONED worker=%s job=%s reason=%s stop_requested=%s", slot.worker_id, task.job_name, result.get("FailureReport", "retry_exhausted"), self.stop_requested, extra={"event": "TASK_ABANDONED", "phase": "solve", "worker": slot.worker_id, "job": task.job_name, "reason": result.get("FailureReport", "retry_exhausted"), "stop_requested": self.stop_requested})
        self.logger.error(
            "任务结束 | TASK_DONE worker=%s job=%s status=Failure attempts=%d elapsed_seconds=%.3f",
            slot.worker_id,
            task.job_name,
            task.retry_count + 1,
            time.monotonic() - started_at, extra={"event": "TASK_DONE", "phase": "solve", "worker": slot.worker_id, "job": task.job_name, "attempts": task.retry_count + 1, "elapsed_seconds": time.monotonic() - started_at})
        return result

    def _drain_tasks(self, slot: _WorkerSlot) -> None:
        while self.state is ManagerState.RUNNING and not self.stop_requested:
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
            self.logger.info("开始关闭 Worker 池 | MANAGER_STOP_START workers=%d", len(slots), extra={"event": "MANAGER_STOP_START", "phase": "shutdown", "workers": len(slots)})

        def stop_slot(slot: _WorkerSlot):
            try:
                slot.worker.stop()
            except Exception as exc:
                self.logger.exception("Worker 关闭失败 | worker=%s project=%s", slot.worker_id, self.currProjectDir)
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
            "MANAGER_STOPPED workers=%d errors=%d", len(slots), len(stop_errors), extra={"event": "MANAGER_STOPPED", "phase": "shutdown", "workers": len(slots), "errors": len(stop_errors)})
        if self._standalone_overview is not None:
            try:
                self._standalone_overview.update(status='RECOVERY_REQUIRED' if stop_errors else 'STOPPED',
                                                  stop_errors=len(stop_errors))
            except (OSError, ValueError):
                self.logger.warning('运行摘要未能更新，请核对完整日志', exc_info=True)
        if stop_errors:
            raise RuntimeError(
                f"{len(stop_errors)} CST worker(s) did not stop cleanly"
            ) from stop_errors[0]

    def adopt_result(self, task_id: str) -> None:
        path = self._received_paths.get(task_id)
        if path is not None:
            from .checkpoint_adoption import mark_adopted
            mark_adopted(path, self.run_store, task_id)

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
            workers = [slot.worker for slot in self._slots]
        self._clear_queue(self._task_queue)
        for worker in workers:
            publish_stop = getattr(worker, 'request_stop', None)
            if publish_stop is not None:
                try:
                    publish_stop()
                except Exception:
                    self.logger.exception("Worker停止请求发布失败；保留本任务并等待标准收尾")
        self.logger.info("Manager 已接受安全停止请求 | project=%s", self.currProjectDir)

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
