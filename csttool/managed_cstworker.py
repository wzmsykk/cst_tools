"""Production long-lived CST worker using the versioned file protocol."""

from __future__ import annotations

import logging
from dataclasses import replace
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import Any, Mapping

from install_compat import resource_path

from .postprocess_cst import CstPostProcessor
from .configuration import write_json_atomic, read_json
from .cst_progress import CstLogProgressMonitor, CstLogProgressParser
from .vb_codec import quote_vb_string
from .logging_config import ContextLogger, log_failure
from .worker_models import WorkerConfig, SimulationResult
from .cst_process_env import cst_process_environment
from .resource_usage import record_worker_usage
from .native_progress import NativeProgressTracker
from .solver_output import SolverOutputTracker
from .run_store import RunStore
from .result_reconciliation import file_hash
from .cst_memory_guard import MemoryGuardPolicy, MemorySamplingError, SustainedMemoryGuard, owned_process_memory
from .diagnostics import archive_task, write_run_manifest, write_failure_report
from .runtime_protocol import (
    Acknowledge,
    CompletionStatus,
    FileProtocol,
    Task,
    atomic_publish,
    decode_completion,
    encode_ack,
    publish_ack_idempotently,
    new_session_id,
)


class ManagedWorkerShutdownError(RuntimeError):
    pass


class ManagedAcknowledgmentPending(RuntimeError):
    """Completion was received; automatic solver replay is unsafe."""
    completed_result_pending = True

    def __init__(self, receipt, cause):
        self.receipt_path = Path(receipt)
        super().__init__(f"ACK_PENDING: receipt={receipt}; {cause}")


class ManagedCSTWorker:
    START_TIMEOUT = 120.0
    # Solves may legitimately take hours; only lifecycle waits are bounded.
    TASK_TIMEOUT: float | None = None
    STOP_TIMEOUT = 120.0

    def __init__(self, worker_id: str, config: WorkerConfig, logger=None):
        if isinstance(config, Mapping):
            config = WorkerConfig.from_mapping(config)
        self.ID = worker_id
        self.logger = logger or logging.getLogger(__name__)
        worker_root = config.task_directory.resolve()
        self.session_id = new_session_id()
        self.logger = ContextLogger(self.logger, {
            "worker": worker_id, "session": self.session_id,
        })
        self.root = worker_root / self.session_id
        self.observation_root = (config.run_directory / 'workers' / worker_id / self.session_id
                                 if config.run_directory is not None else self.root)
        self.run_store = (RunStore(config.project_directory or worker_root, config.run_directory)
                          if config.run_directory is not None else None)
        self.result_root = config.result_directory.resolve() / f"worker_{worker_id}"
        self.source_project = config.project_path.resolve()
        self.executable = config.executable.resolve()
        self.parameter_definitions = tuple(config.parameters)
        self.execution_fingerprint = config.execution_fingerprint
        self._field_reference_result = config.field_reference_result
        self._field_match_policy = config.field_match_policy
        self._vacuum_domain = config.vacuum_domain
        self._vacuum_reference_store = config.vacuum_reference_store
        self._domain_jobs = []
        if config.vacuum_domain is not None:
            from .vacuum_domain_registry import validate_managed_domain_options
            self._vacuum_domain = validate_managed_domain_options(config.vacuum_domain)
        if config.field_reference_result is not None:
            from .mode_matching import MatchPolicy
            if config.field_match_policy is None:
                raise ValueError('field diagnostic requires an explicit matching policy')
            MatchPolicy(**config.field_match_policy)
        self.postprocess = CstPostProcessor()
        self.postprocess_settings = list(config.postprocess)
        self.postprocess.configure(config.postprocess)
        self.protocol = FileProtocol(self.root / "protocol")
        self.task_path = self.protocol.root / "current.task"
        self.completion_path = self.protocol.root / "current.completion"
        self.ack_path = self.protocol.root / "current.ack"
        self.marker_path = self.root / "worker.state"
        self.stop_request_path = self.protocol.root / "stop.request"
        self.stop_ack_path = self.protocol.root / "stop.ack"
        self.project_path = self.root / "worker-input.cst"
        self.macro_path = self.root / "runtime_managed_worker_v1.bas"
        self.batch_script_path = self.project_path.with_suffix('') / 'Model' / '3D' / 'Model.run'
        self.log_path = self.observation_root / "cst.log"
        self.pid_path = self.root / "worker.pid"
        self._lock = threading.RLock()
        self._stopping = False
        self._process: subprocess.Popen | None = None
        self._memory_guard_policy = config.memory_guard
        self._log_stream = None
        self._run_in_background = config.background
        self._last_window_check = 0.0
        self._progress_callback = config.progress_callback
        self._active_task_context: dict[str, Any] = {}
        self._progress_monitor: CstLogProgressMonitor | None = None

        self.root.mkdir(parents=True, exist_ok=True)
        self.observation_root.mkdir(parents=True, exist_ok=True)
        self.result_root.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "cst_log": self.log_path, "macro": self.macro_path,
            "batch_script": self.batch_script_path,
            "project": self.project_path, "task": self.task_path,
            "completion": self.completion_path, "ack": self.ack_path,
            "state": self.marker_path, "stop_request": self.stop_request_path,
            "stop_ack": self.stop_ack_path, "results": self.result_root,
            "last_good_parameters": Path(str(self.project_path) + '.last-good-parameters.tsv'),
            "recovery_snapshot": Path(str(self.project_path) + '.recovered.cst'),
            "recovery_receipt": Path(str(self.project_path) + '.recovery-saved'),
        }
        manifest = write_run_manifest(self.observation_root / "diagnostics.json", config, artifacts,
                                      context={"worker": worker_id, "session": self.session_id})
        self.logger.info("Worker 诊断入口已保存 | WORKER_DIAGNOSTICS path=%s", manifest,
                         extra={"event": "WORKER_DIAGNOSTICS", "phase": "prepare", "artifacts": {**artifacts, "manifest": manifest}})
        shutil.copy2(self.source_project, self.project_path)
        self._build_macro()
        try:
            self._start()
        except Exception:
            # Keep PID/protocol files for explicit recovery; never replace
            # the startup error with a cleanup exception or force-kill CST.
            self._diagnose_failure("startup")
            try:
                self._close_log()
            except Exception:
                self.logger.exception("启动失败后的资源关闭失败", extra={"event": "WORKER_CLEANUP_FAILED", "phase": "shutdown"})
            self.logger.exception("CST 启动失败，保留会话供恢复", extra={
                "event": "WORKER_START_FAILED", "phase": "prepare",
                "artifacts": {"session_root": self.root, "cst_log": self.log_path},
            })
            raise

    def _diagnose_failure(self, phase):
        try:
            observation = getattr(self, 'observation_root', self.root)
            path = write_failure_report(observation, phase=phase,
                process=getattr(self, '_process', None),
                context={"worker": self.ID, "session": self.session_id,
                         **getattr(self, '_active_task_context', {})},
                paths={name: getattr(self, name, None) for name in (
                    'log_path', 'marker_path', 'task_path', 'completion_path',
                    'ack_path', 'stop_request_path', 'stop_ack_path')} | {
                        'lifecycle_log': observation / 'lifecycle.log',
                        'received_receipt': observation / 'received' / (
                            str(getattr(self, '_active_task_context', {}).get('task_id', 'unknown')) + '.json'),
                        'ack_receipt': Path(str(self.ack_path) + '.' + str(
                            getattr(self, '_active_task_context', {}).get('task_id', 'unknown')) + '.accepted'),
                    })
            self.logger.error("CST 失败诊断已保存 | phase=%s path=%s", phase, path,
                              extra={"event": "WORKER_FAILURE_DIAGNOSTICS", "phase": phase,
                                     "artifacts": {"failure_report": path}})
        except Exception:
            self.logger.exception("失败诊断收集失败，保留原始异常", extra={
                "event": "WORKER_DIAGNOSTICS_FAILED", "phase": phase})

    @classmethod
    def create(cls, worker_id, config, logger):
        return cls(worker_id, config, logger)

    def _build_macro(self) -> None:
        codec = Path(resource_path("data/runtime_protocol_v1.vb")).read_text(
            encoding="utf-8"
        )
        main = Path(resource_path("data/runtime_managed_worker_v1_main.vb")).read_text(
            encoding="utf-8"
        )
        replacements = {
            "%PROJECT_PATH%": quote_vb_string(self.project_path),
            "%SESSION_ID%": self.session_id,
            "%TASK_PATH%": quote_vb_string(self.task_path),
            "%COMPLETION_PATH%": quote_vb_string(self.completion_path),
            "%ACK_PATH%": quote_vb_string(self.ack_path),
            "%MARKER_PATH%": quote_vb_string(self.marker_path),
            "%LIFECYCLE_PATH%": quote_vb_string(getattr(self, 'observation_root', self.root) / 'lifecycle.log'),
            "%STOP_REQUEST_PATH%": quote_vb_string(self.stop_request_path),
            "%STOP_ACK_PATH%": quote_vb_string(self.stop_ack_path),
            "%RESULT_ROOT%": quote_vb_string(str(self.result_root) + "\\"),
        }
        for placeholder, value in replacements.items():
            main = main.replace(placeholder, value)
        generated = "".join(self.postprocess.render_vb(cooperative_stop=True))
        output = (
            "'#Language \"WWB-COM\"\n\nOption Explicit\n\n"
            + codec
            + "\n"
            + main
            + "\n"
            + generated
        )
        if "%" in main or output.lower().count("sub main") != 1:
            raise ValueError("managed worker macro contains unresolved placeholders")
        self.macro_path.write_text(output, encoding="ascii", newline="\n")
        batch_script = self.project_path.with_suffix('') / 'Model' / '3D' / 'Model.run'
        batch_script.parent.mkdir(parents=True, exist_ok=True)
        batch_script.write_text(output, encoding='ascii', newline='\n')

    def _launch_command(self) -> list[str]:
        # Documented -b runs Model/3D/Model.run in the already loaded project.
        return [str(self.executable), '-m', '-b', str(self.project_path)]

    def _start(self) -> None:
        self._log_stream = self.log_path.open("wb", buffering=0)
        self._process = subprocess.Popen(
            self._launch_command(),
            env=cst_process_environment(),
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            **self._background_startup_options(),
        )
        self.pid_path.write_text(str(self._process.pid), encoding="ascii")
        if callable(self._progress_callback):
            parser = CstLogProgressParser(self.ID, self._progress_context)
            self._progress_monitor = CstLogProgressMonitor(
                self.log_path, parser, self._emit_redirected_progress
            )
            self._progress_monitor.start()
        self._wait_for_marker("ready", self.START_TIMEOUT)
        self.logger.info("CST 进程已启动 | worker=%s session=%s pid=%s project=%s", self.ID, self.session_id, self._process.pid, self.source_project)

    def _emit_redirected_progress(self, event):
        native = getattr(self, '_native_progress', None)
        if native is not None and native.last_observation is not None:
            return  # Native state is authoritative for observational GUI progress.
        callback = getattr(self, '_progress_callback', None)
        if callable(callback):
            callback(replace(event, session_id=self.session_id, source='stdout'))

    def _background_startup_options(self) -> dict[str, Any]:
        """Isolate console signals and optionally start CST minimized."""
        if os.name != "nt":
            return {}
        options: dict[str, Any] = {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
        }
        if not self._run_in_background:
            return options
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        # SW_SHOWMINNOACTIVE: minimized and does not activate the CST window.
        startupinfo.wShowWindow = 7
        options["startupinfo"] = startupinfo
        return options

    def _keep_window_minimized(self) -> None:
        """Re-minimize visible CST windows that appear while a task is running."""
        if (
            not self._run_in_background
            or os.name != "nt"
            or self._process is None
            or self._process.poll() is not None
        ):
            return
        now = time.monotonic()
        if now - self._last_window_check < 0.5:
            return
        self._last_window_check = now

        try:
            import ctypes

            user32 = ctypes.windll.user32
            target_pid = self._process.pid
            callback_type = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
            )

            def minimize(hwnd, _lparam):
                process_id = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
                if (
                    process_id.value == target_pid
                    and user32.IsWindowVisible(hwnd)
                    and not user32.IsIconic(hwnd)
                ):
                    user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                return True

            user32.EnumWindows(callback_type(minimize), 0)
        except Exception:
            self.logger.debug(
                "Unable to enforce minimized CST window for worker %s",
                self.ID,
                exc_info=True,
            )

    def _wait_for_marker(self, expected: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._ensure_running()
            self._keep_window_minimized()
            if self.marker_path.exists():
                marker = self.marker_path.read_text(encoding="ascii").strip()
                if marker == expected:
                    return
                if marker.startswith("failure:"):
                    raise RuntimeError(marker)
            time.sleep(0.1)
        raise TimeoutError(f"managed CST worker timed out waiting for {expected}")

    def _ensure_running(self) -> None:
        if self._process is None:
            raise RuntimeError("managed CST worker has not started")
        code = self._process.poll()
        if code is not None:
            raise RuntimeError(f"managed CST worker exited with code {code}")

    def _expression_names(self, params: Mapping[str, Any]) -> frozenset[str]:
        definitions = {item["name"]: item for item in self.parameter_definitions}
        return frozenset(
            name
            for name, value in params.items()
            if definitions.get(name, {}).get("type") == "expression"
            or not self._is_number(value)
        )

    def _progress_context(self) -> dict[str, Any]:
        return dict(self._active_task_context)

    @staticmethod
    def _is_number(value: object) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    def set_attempt_context(self, job_id, attempt_no):
        self._attempt_context = {'job_id': job_id, 'attempt_no': attempt_no}

    @record_worker_usage
    def run_task(self, result_name: str, *, params: Mapping[str, Any]) -> SimulationResult:
        with self._lock:
            if self._stopping:
                raise RuntimeError("managed CST worker is stopping")
            self._wait_for_marker("ready", self.START_TIMEOUT)
            task = Task.create(
                self.session_id,
                params,
                expression_names=self._expression_names(params),
            )
            payload = archive_task(self.root, task, result_name)
            if hasattr(self, 'postprocess_settings'):
                write_json_atomic(self.root / 'task-context.json', {
                    'schema_version': 1, 'task_id': task.task_id, 'session_id': task.session_id,
                    'job': result_name, 'parameters': dict(params),
                    'postprocess': self.postprocess_settings,
                    'result_root': str((self.result_root / task.task_id).resolve()),
                    'receipt_path': str((getattr(self, 'observation_root', self.root) / 'received' / f'{task.task_id}.json').resolve()),
                    'execution_fingerprint': self.execution_fingerprint,
                    'optional_analysis_pending': bool(getattr(self, '_field_reference_result', None)
                                                      or getattr(self, '_vacuum_domain', None)),
                })
            if getattr(self, 'run_store', None) is not None:
                self.run_store.event(task.task_id, 'submitted', worker=self.ID,
                                     session=self.session_id, job=result_name, parameters=dict(params),
                                     **getattr(self, '_attempt_context', {}))
            if getattr(self, '_resource_usage', None) is not None:
                self._resource_usage.identity['task_id'] = task.task_id
            self._active_task_context = {
                "task_id": task.task_id,
                "interval_lo": self._progress_number(params.get("fmin")),
                "interval_hi": self._progress_number(params.get("fmax")),
            }
            started_at = time.monotonic()
            self._native_progress = NativeProgressTracker(
                self.project_path.with_suffix('') / 'Result' / 'progress.log',
                getattr(self, 'observation_root', self.root) / 'native_progress' / task.task_id,
                self.ID, self.session_id, task, self.logger,
                getattr(self, '_progress_callback', None),
            )
            self._solver_output = SolverOutputTracker(
                self.project_path.with_suffix('') / 'Result' / 'output.txt',
                getattr(self, 'observation_root', self.root) / 'native_progress' / task.task_id, task, self.logger,
            )
            self.marker_path.write_text(
                f"dispatched:{task.task_id}", encoding="ascii"
            )
            atomic_publish(self.task_path, payload)
            self.logger.info("任务已提交，等待CST完成计算",
                extra={"event": "WORKER_TASK_DISPATCH", "phase": "solve", "worker": self.ID, "session": self.session_id, "task": task.task_id, "job": result_name, "fmin": params.get("fmin"), "fmax": params.get("fmax")})
            try:
                completion = self._wait_completion(task)
            except Exception as exc:
                self._diagnose_failure("completion")
                log_failure(self.logger, "未能确认计算完成；请检查完成协议与CST诊断", exc,
                    extra={"event": "CST_COMPLETION_FAILED", "phase": "solve", "task": task.task_id, "job": result_name,
                           "recovery_hint":"先核对本任务进程及完成标记，不因等待失败重复求解"})
                self._active_task_context = {}
                raise
            self.logger.debug("收到CST完成标记，开始核对结果", extra={"event": "CST_COMPLETION", "phase": "solve", "task": task.task_id, "job": result_name, "status": completion.status.value})
            task_result_root = self.result_root / task.task_id
            project_snapshot = task_result_root / "project.cst"
            field_artifacts = []
            try:
                if completion.status is CompletionStatus.SUCCESS:
                    if not project_snapshot.is_file() or project_snapshot.stat().st_size == 0:
                        raise FileNotFoundError(
                            f"CST task did not publish a project snapshot: {project_snapshot}"
                        )
                    self.postprocess.set_result_directory(task_result_root)
                    self.postprocess.set_cst_run_result_directory(task_result_root / "project")
                    postprocess_result = self.postprocess.read_all_results()
                    field_artifacts = [item for item in postprocess_result
                        if isinstance(item.get('value'), dict) and item['value'].get('kind') == 'field-artifact']
                    postprocess_result = [item for item in postprocess_result if item not in field_artifacts]
                    self.logger.info("后处理结果已读取，等待保存接收记录并确认任务", extra={"event": "RESULT_READ_DONE", "phase": "readout", "task": task.task_id, "job": result_name, "results": len(postprocess_result), "snapshot": project_snapshot})
                    status = "Success"
                    failure = None
                else:
                    postprocess_result = None
                    status = "Failure"
                    failure = f"{completion.error_code.value}: {completion.error_message}"
            except Exception as exc:
                log_failure(self.logger, "后处理结果不可用；本次任务不能作为成功结果接收", exc,
                    extra={"event": "RESULT_READ_FAILED", "phase": "readout", "task": task.task_id, "job": result_name,
                           "recovery_hint":"检查结果文件和后处理要求，不能据此认定求解器未运行"})
                postprocess_result = None
                status = "Failure"
                failure = f"RESULT_READ_FAILED: {type(exc).__name__}: {exc}"
            finally:
                receipt_path = getattr(self, 'observation_root', self.root) / 'received' / f'{task.task_id}.json'
                received = {
                    'schema_version': 1, 'phase': 'received',
                    'task_id': task.task_id, 'session_id': task.session_id,
                    'job': result_name, 'parameters': dict(params),
                    'status': status, 'failure': failure, 'postprocess': postprocess_result,
                    'field_artifacts': field_artifacts,
                    'snapshot': str(project_snapshot.resolve()) if project_snapshot.exists() else None,
                    'snapshot_sha256': file_hash(project_snapshot) if status == 'Success' else None,
                    'workspace': str(self.root),
                    'execution_fingerprint': getattr(self, 'execution_fingerprint', None),
                    'optional_analysis_pending': bool(getattr(self, '_field_reference_result', None)
                                                      or getattr(self, '_vacuum_domain', None)),
                }
                try:
                    # Persist result consumption BEFORE authorizing VBA cleanup.
                    write_json_atomic(receipt_path, received)
                    if getattr(self, 'run_store', None) is not None:
                        self.run_store.event(task.task_id, 'received', result_status=status)
                        self.run_store.artifacts(task.task_id, received=receipt_path,
                            snapshot=project_snapshot, protocol=self.protocol.root,
                            log=self.log_path, native_progress=getattr(self, 'observation_root', self.root) / 'native_progress' / task.task_id)
                    publish_ack_idempotently(
                        self.ack_path,
                        Acknowledge(task.task_id, task.session_id),
                    )
                    self.logger.debug("接收记录已保存，任务确认已发送，等待CST回到就绪状态", extra={"event": "TASK_ACK_PUBLISHED", "phase": "ack", "task": task.task_id, "job": result_name})
                    self._wait_for_marker("ready", self.START_TIMEOUT)
                    write_json_atomic(receipt_path, {**received, 'phase': 'acknowledged'})
                    if getattr(self, 'run_store', None) is not None:
                        self.run_store.event(task.task_id, 'acknowledged')
                    self.logger.info("任务确认完成，CST已回到就绪状态", extra={"event": "TASK_ACK_READY", "phase": "ack", "task": task.task_id, "job": result_name, "result_status":status})
                except Exception as exc:
                    if getattr(self, 'run_store', None) is not None:
                        try:
                            self.run_store.event(task.task_id, 'ack_pending', error=str(exc))
                        except (OSError, ValueError):
                            self.logger.warning('待确认索引写入失败，保留接收记录与原始异常', exc_info=True)
                    self._diagnose_failure("ack")
                    log_failure(self.logger, "任务确认未完成；保存状态请核对接收记录，先恢复会话再决定是否继续", exc,
                        extra={"event": "TASK_ACK_FAILED", "phase": "ack", "task": task.task_id, "job": result_name,
                               "receipt":str(receipt_path), "result_status":status,
                               "recovery_hint":"检查接收记录是否实际保存，不直接重复计算"})
                    raise ManagedAcknowledgmentPending(receipt_path, exc) from exc
                finally:
                    self._active_task_context = {}
            field_diagnostic = None
            domain_registration = None
            if status == "Success":
                task_result_root, project_snapshot = self._name_result_archive(
                    task, result_name, task_result_root, postprocess_result
                )
                self.postprocess.set_result_directory(task_result_root)
                self.postprocess.set_cst_run_result_directory(project_snapshot.with_suffix(""))
                for item in field_artifacts:
                    value = item.get('value')
                    if isinstance(value, dict) and value.get('kind') == 'field-artifact':
                        value['context'] = {'task_id': task.task_id, 'session_id': self.session_id,
                                            'snapshot_sha256': received['snapshot_sha256']}
                if field_artifacts:
                    available = sum(item['value']['status']=='available' for item in field_artifacts)
                    self.logger.info('场工件已归档 | FIELD_ARTIFACTS_READY task=%s available=%d unavailable=%d directory=%s',
                        task.task_id,available,len(field_artifacts)-available,task_result_root,
                        extra={'event':'FIELD_ARTIFACTS_READY','phase':'field-analysis','task':task.task_id,
                               'available':available,'unavailable':len(field_artifacts)-available})
                if getattr(self, 'run_store', None) is not None:
                    try:
                        self.run_store.artifacts(task.task_id, snapshot=project_snapshot,
                                                 result_directory=task_result_root)
                        self.run_store.artifacts(task.task_id, **{
                            f"field_{item['id']}":task_result_root/item['value']['filename']
                            for item in field_artifacts if item['value']['status']=='available'})
                    except OSError:
                        self.logger.warning('存档映射更新失败，不重算已完成任务', exc_info=True)
                try:
                    write_json_atomic(receipt_path, {**received, 'phase': 'acknowledged',
                                                   'snapshot': str(project_snapshot.resolve())})
                except OSError:
                    self.logger.warning('接收记录存档路径更新失败，原始记录仍保留', exc_info=True)
                field_diagnostic = self._run_optional_field_diagnostic(task, task_result_root, field_artifacts)
                if getattr(self,'_vacuum_domain',None) is not None:
                    destination = task_result_root/'vacuum-domain'
                    domain_registration = {'status':'pending-after-stop',
                        'path':str(destination/'domain-registration.json'),
                        'tracking_input':str(task_result_root/'vacuum-tracking-input.json')}
                    if self._vacuum_domain.get('matching'):
                        domain_registration['matching_report'] = str(task_result_root/'vacuum-mode-matching.json')
                    self._domain_jobs.append((task.task_id,project_snapshot,task_result_root,field_artifacts))
                    try:
                        write_json_atomic(task_result_root/'vacuum-domain-pending.json',domain_registration)
                    except OSError:
                        self.logger.warning('可选域登记待办写入失败，已确认求解不重算 | task=%s',task.task_id,exc_info=True)
                if field_artifacts or field_diagnostic or domain_registration:
                    try:
                        latest = read_json(receipt_path)
                        write_json_atomic(receipt_path, {**latest, 'field_artifacts': field_artifacts,
                            'field_diagnostic': field_diagnostic, 'domain_registration': domain_registration,
                            'result_directory': str(task_result_root.resolve()),
                            'optional_analysis_pending': bool(getattr(self, '_vacuum_domain', None))})
                    except Exception as exc:
                        # Mark this as an already-completed result, so Manager
                        # cannot replay Solver to repair an analysis receipt.
                        raise ManagedAcknowledgmentPending(receipt_path, exc) from exc
            log_method = self.logger.info if status == "Success" else self.logger.error
            log_method(
                "任务完成，结果已接收并确认" if status == "Success" else "任务未成功，失败信息已接收；请检查原因",
                extra={"event": "WORKER_TASK_COMPLETE", "phase": "solve", "worker": self.ID, "task": task.task_id, "status": status, "elapsed_seconds": time.monotonic() - started_at, "failure": failure or "none", "job": result_name})
            return SimulationResult(
                self.ID, status, result_name, dict(params), postprocess_result,
                failure, project_snapshot.resolve() if status == "Success" else None,
                task_id=task.task_id, result_directory=task_result_root.resolve(),
                receipt_path=receipt_path,
                field_diagnostic=field_diagnostic,
                field_artifacts=field_artifacts or None,
                domain_registration=domain_registration,
            )

    def _run_optional_field_diagnostic(self, task, directory, postprocess):
        """Post-Ack diagnostics cannot replay or invalidate a completed solver task."""
        reference = getattr(self, '_field_reference_result', None)
        if reference is None:
            return None
        from .configuration import read_json
        from .field_artifacts import artifacts_from_result
        from .field_diagnostics import run_field_diagnostic
        from .mode_matching import MatchPolicy
        destination = directory / 'field-diagnostic.json'
        try:
            previous = read_json(reference)
            ref_directory = previous.get('ResultDirectory', previous.get('result_directory'))
            if not ref_directory:
                raise ValueError('reference result directory missing')
            candidates = artifacts_from_result(directory, postprocess,
                                                expected_context={'task_id': task.task_id, 'session_id': self.session_id})
            ref = artifacts_from_result(ref_directory, previous.get('FieldArtifacts') or previous.get('PostProcessResult', []))
            result = run_field_diagnostic(ref, candidates, MatchPolicy(**self._field_match_policy), destination,
                context={'task_id': task.task_id, 'session': self.session_id, 'worker': self.ID},
                run_store=getattr(self,'run_store',None), cancelled=lambda: self._stopping, logger=self.logger)
        except Exception as exc:
            result = {'status': 'incomplete', 'reason': f'{type(exc).__name__}: {exc}'}
            self.logger.warning('可选场诊断未完成，保留求解结果 | FIELD_DIAGNOSTIC_INCOMPLETE task=%s reason=%s',
                                task.task_id,result['reason'],extra={'event':'FIELD_DIAGNOSTIC_INCOMPLETE','phase':'field-analysis','task':task.task_id})
            try:
                write_json_atomic(destination,result)
            except OSError:
                self.logger.warning('场诊断记录写入失败 | FIELD_DIAGNOSTIC_PERSIST_FAILED task=%s',task.task_id,exc_info=True,
                                    extra={'event':'FIELD_DIAGNOSTIC_PERSIST_FAILED','phase':'field-analysis','task':task.task_id})
        return {**result, 'path': str(destination)}

    def _name_result_archive(self, task, resultname, directory, postprocess):
        """Name a confirmed Backup and its CST companion directory together."""
        label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(resultname)).strip(" .")[:40]
        label = label or "task"
        frequencies = []
        for item in postprocess or ():
            if str(item.get("resultName", "")).casefold() == "frequency":
                value = item.get("value")
                candidates = value.values() if isinstance(value, dict) else (value,)
                for candidate in candidates:
                    number = self._progress_number(candidate)
                    if number is not None and math.isfinite(number):
                        frequencies.append(number)
        if len(frequencies) == 1:
            label += f"__f_{frequencies[0]:.6f}MHz"
        # Full protocol identity prevents repeated jobs/retries from colliding.
        destination = self.result_root / f"{label}__{task.task_id}"
        snapshot_name = f"{label}.cst"
        original = directory / "project.cst"
        companion = directory / "project"
        renamed = directory / snapshot_name
        renamed_companion = renamed.with_suffix("")
        root = self.result_root.resolve()
        if directory.resolve().parent != root or destination.resolve().parent != root:
            raise ValueError("result archive must stay within the worker result directory")
        moved = []
        try:
            if destination.exists():
                raise FileExistsError(destination)
            if original != renamed:
                original.rename(renamed)
                moved.append((renamed, original))
            if companion.exists() and companion != renamed_companion:
                companion.rename(renamed_companion)
                moved.append((renamed_companion, companion))
            directory.rename(destination)
        except OSError:
            for current, previous in reversed(moved):
                current.rename(previous)
            self.logger.warning("无法重命名结果存档，保留原路径：%s", directory, exc_info=True)
            destination, snapshot_name = directory, "project.cst"
        snapshot = destination / snapshot_name
        try:
            write_json_atomic(destination / "task_result.json", {
                "schemaVersion": 1,
                "taskId": task.task_id,
                "sessionId": task.session_id,
                "taskName": resultname,
                "parameters": {item.name: item.value for item in task.parameters},
                "projectSnapshot": snapshot_name,
                "postprocess": postprocess,
            })
        except (OSError, TypeError, ValueError):
            self.logger.warning("无法保存存档结果索引：%s", destination, exc_info=True)
        return destination, snapshot

    @staticmethod
    def _progress_number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _wait_completion(self, task: Task):
        started = time.monotonic()
        policy = getattr(self, "_memory_guard_policy", MemoryGuardPolicy())
        guard = SustainedMemoryGuard(policy)
        next_memory_sample = started
        deadline = None if self.TASK_TIMEOUT is None else started + self.TASK_TIMEOUT
        next_report = started + 30.0
        next_heartbeat = started + 600.0
        while deadline is None or time.monotonic() < deadline:
            self._ensure_running()
            self._keep_window_minimized()
            if getattr(self, '_native_progress', None) is not None:
                self._native_progress.poll()
            if getattr(self, '_solver_output', None) is not None:
                self._solver_output.poll()
            if getattr(self, '_resource_usage', None) is not None:
                self._resource_usage.sample(getattr(self, '_process', None))
            if time.monotonic() >= next_report or time.monotonic() >= next_heartbeat:
                elapsed = time.monotonic() - started
                log_size = self.log_path.stat().st_size if self.log_path.exists() else None
                heartbeat = time.monotonic() >= next_heartbeat
                self.logger.log(logging.INFO if heartbeat else logging.DEBUG,
                    "CST尚未返回完成标记，继续等待",
                    extra={"event": "CST_WAIT_PROGRESS", "phase": "solve", "task": task.task_id,
                           "elapsed_seconds": elapsed, "log_bytes": log_size,
                           "timeout_seconds": self.TASK_TIMEOUT})
                if heartbeat:
                    next_heartbeat = time.monotonic() + 600.0
                next_report = time.monotonic() + 30.0
            if self.completion_path.exists():
                completion = decode_completion(
                    self.completion_path.read_text(encoding="utf-8")
                )
                if (completion.task_id, completion.session_id) != (
                    task.task_id,
                    task.session_id,
                ):
                    raise RuntimeError("completion belongs to another task")
                if getattr(self, '_solver_output', None) is not None:
                    self._solver_output.poll(force=True)
                if getattr(self, '_native_progress', None) is not None:
                    self._native_progress.poll(force=True)
                return completion
            now = time.monotonic()
            if policy.enabled and now >= next_memory_sample:
                next_memory_sample = now + policy.sample_seconds
                self._check_memory_guard(task, guard, now)
            time.sleep(0.1)
        raise TimeoutError(f"timed out waiting for CST task {task.task_id}")

    def _check_memory_guard(self, task, guard, now):
        process = getattr(self, "_process", None)
        if process is None:
            return
        try:
            sample = owned_process_memory(process)
        except (OSError, MemorySamplingError) as exc:
            # A failed sample must break continuous-pressure evidence.
            guard.high_since = None
            if not getattr(self, "_memory_sample_error_reported", False):
                self.logger.warning("CST 内存监测不可用，禁用本次样本清理判断：%s", exc)
                self._memory_sample_error_reported = True
            return
        if sample is None:
            guard.high_since = None
            return
        memory, physical = sample
        size = self.log_path.stat().st_size if self.log_path.exists() else None
        native = getattr(self, '_native_progress', None)
        if native is not None:
            size = (size, native.last_observation)
        if not guard.observe(now, memory, physical, size):
            return
        # Completion wins if it appeared during sampling; never discard success.
        if self.completion_path.exists():
            return
        self.logger.error("CST 内存异常且持续无日志进展，开始安全退出 | task=%s pid=%s memory_bytes=%s physical_bytes=%s", task.task_id, process.pid, memory, physical)
        self._diagnose_failure("memory-guard")
        try:
            self.stop()
        except ManagedWorkerShutdownError:
            self.logger.error("标准退出失败，紧急清理本会话 CST 进程树 | task=%s pid=%s", task.task_id, process.pid)
            self.emergency_terminate()
        raise RuntimeError("CST_MEMORY_GUARD: sustained extreme memory and stalled log; replay from confirmed snapshot")

    def request_stop(self) -> None:
        """Publish cancellation without waiting for the running task's lock."""
        self.protocol.request_stop(self.session_id)

    def stop(self) -> bool:
        with self._lock:
            if self._process is None:
                return True
            if self._process.poll() is not None:
                if self.protocol.read_stop_ack(self.session_id) is None or not self._stop_exit_is_confirmed():
                    self._close_log()
                    self._diagnose_failure("shutdown")
                    raise ManagedWorkerShutdownError("CST exited without verified StopAck and exit code 0")
                self.logger.debug("CST 进程已结束，无需重复退出 | WORKER_ALREADY_EXITED worker=%s session=%s returncode=%s", self.ID, self.session_id, self._process.poll(), extra={"event": "WORKER_ALREADY_EXITED", "phase": "readout", "worker": self.ID, "session": self.session_id, "returncode": self._process.poll()})
                self._close_log()
                self._finish_domain_registration()
                return True
            self._stopping = True
            self.logger.info(
                "已请求CST标准退出，等待保存回执与进程结束",
                extra={"event": "WORKER_STOP_REQUEST", "phase": "shutdown", "worker": self.ID, "session": self.session_id, "pid": getattr(self._process, "pid", None)})
            if not self.stop_request_path.exists():
                self.protocol.request_stop(self.session_id)
            deadline = time.monotonic() + self.STOP_TIMEOUT
            while time.monotonic() < deadline:
                if self.protocol.read_stop_ack(self.session_id) is not None:
                    try:
                        self._process.wait(timeout=max(0.1, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        break
                    if not self._stop_exit_is_confirmed():
                        break
                    self._close_log()
                    self.logger.info(
                        "CST标准退出已确认，本会话已关闭", extra={"event": "WORKER_STOPPED", "phase": "shutdown", "worker": self.ID, "session": self.session_id})
                    self._finish_domain_registration()
                    return True
                if self._process.poll() is not None:
                    break
                time.sleep(0.1)

            if self._process.poll() is not None:
                self._close_log()
            self._diagnose_failure("shutdown")
            self.logger.error("CST标准退出未确认；保留会话，请先执行恢复", extra={"event": "WORKER_STOP_FAILED", "phase": "shutdown", "worker": self.ID, "session": self.session_id, "returncode": self._process.poll(), "process_alive": self._process.poll() is None, "timeout_seconds": self.STOP_TIMEOUT, "recovery_hint":"核对StopAck、快照及本任务进程，不强杀独立实例"})
            raise ManagedWorkerShutdownError(
                f"worker {self.ID} did not confirm Save/StopAck/batch exit; " + (
                    "process already exited; reconcile preserved protocol and snapshot"
                    if self._process.poll() is not None else
                    "process is still running; session recovery is required"
                )
            )

    def _finish_domain_registration(self):
        """Only after verified standard exit; optional analysis never replays Solver."""
        if not getattr(self,'_vacuum_domain',None):
            return
        if self._process is None or self._process.poll() is None:
            raise RuntimeError('domain registration requires a confirmed stopped CST process')
        if self.protocol.read_stop_ack(self.session_id) is None or not self._stop_exit_is_confirmed():
            raise RuntimeError('domain registration requires verified StopAck and standard exit')
        from .vacuum_domain_registry import register_vacuum_domain
        from .field_artifacts import SamplingSpec
        jobs = getattr(self,'_domain_jobs',[])
        self._domain_jobs = []
        for task_id,snapshot,directory,fields in jobs:
            destination = directory/'vacuum-domain'
            try:
                result = register_vacuum_domain(self.executable,snapshot,destination,
                    SamplingSpec.from_mapping(self._vacuum_domain['sampling']),
                    geometry_id=self._vacuum_domain['geometry_id'])
                if result['status']=='registered':
                    export_input = directory/'vacuum-fields.json'
                    selected_fields = [item for item in fields if item.get('value',{}).get('field_kind')=='E'
                        and item['value'].get('sampling_id')==result['sampling_id']
                        and item['value'].get('mode') in self._vacuum_domain['modes']]
                    write_json_atomic(export_input,{'ResultDirectory':str(directory),'FieldArtifacts':selected_fields,
                                                    'source_sha256':result['source_sha256']})
                    write_json_atomic(directory/'vacuum-tracking-input.json',{'snapshot_id':task_id,
                        'result_file':str(export_input),'registration_file':str(destination/'domain-registration.json')})
                    if self._vacuum_domain.get('matching'):
                        try:
                            self._run_vacuum_matching(directory)
                        except Exception:
                            self.logger.warning('匹配报告写入或映射失败；域登记与求解结果保留 | task=%s',task_id,exc_info=True)
                elif self._vacuum_domain.get('matching'):
                    write_json_atomic(directory/'vacuum-mode-matching.json',{
                        'status':'unconfirmed','reason':'domain-preflight-rejected',
                        'rejection_reasons':result.get('rejection_reasons',[]),'selected_modes':[],
                        'physical_identity_confirmed':False,'solver_replayed':False})
                if getattr(self,'run_store',None) is not None:
                    self.run_store.artifacts(task_id,domain_registration=destination/'domain-registration.json')
                self.logger.info('归档真空域登记结束 | task=%s status=%s report=%s',
                    task_id,result['status'],destination/'domain-registration.json',
                    extra={'event':'WORKER_VACUUM_DOMAIN','phase':'field-analysis','task':task_id,
                           'status':result['status'],'artifacts':{'registration':str(destination/'domain-registration.json')}})
            except Exception as error:
                self.logger.warning('可选真空域登记未完成，求解结果保留 | task=%s reason=%s',task_id,error)
                try:
                    write_json_atomic(directory/'vacuum-domain-error.json',{'status':'incomplete',
                        'reason':f'{type(error).__name__}: {error}','task_id':task_id,'solver_replayed':False})
                except OSError:
                    self.logger.warning('域登记错误回执写入失败，检查磁盘；CST已确认退出 | task=%s',task_id,exc_info=True)

    def _run_vacuum_matching(self,directory):
        """Frozen anchor across Worker recycling; no solver side effects."""
        from .configuration import read_json
        from .vacuum_mode_tracking import VacuumTrackingDomain,load_tracking_snapshot,VacuumModeTracker
        from .mode_matching import MatchPolicy
        matching = self._vacuum_domain['matching']
        output = directory/'vacuum-mode-matching.json'
        descriptor = {}
        try:
            domain = VacuumTrackingDomain(self._vacuum_domain['geometry_id'],'PEC','Vacuum',True,
                'native registered inventory','native registered full bounds',matching['sampling_evidence'])
            descriptor = read_json(directory/'vacuum-tracking-input.json')
            candidate = load_tracking_snapshot(descriptor,domain,base=directory)
            policy = MatchPolicy(**matching['policy'])
            if matching['reference_strategy']=='external':
                anchor = Path(matching['reference_file'])
                if file_hash(anchor) != matching['reference_sha256']:
                    raise ValueError('external reference descriptor changed')
            else:
                anchor = getattr(self,'_vacuum_reference_store',None) or self.observation_root/'vacuum-reference.json'
                if not anchor.exists():
                    VacuumModeTracker(candidate,domain,policy)  # Validate before publishing anchor.
                    write_json_atomic(anchor,descriptor)
                    from dataclasses import asdict
                    result = {'schema_version':1,'status':'reference-established','reason':'first-valid-fixed-anchor',
                              'selected_modes':[],'reference':descriptor,'physical_identity_confirmed':False,
                              'policy_calibrated':False,'solver_replayed':False,
                              'domain':asdict(domain),'policy':asdict(policy),'reference_strategy':'fixed-anchor'}
                    write_json_atomic(output,result)
                    self.logger.info('固定模式参考已建立 | snapshot=%s report=%s',candidate.snapshot_id,output,
                        extra={'event':'WORKER_VACUUM_MATCH','phase':'field-analysis','status':result['status'],
                               'artifacts':{'matching':str(output)}})
                    if getattr(self,'run_store',None) is not None:
                        self.run_store.artifacts(descriptor['snapshot_id'],mode_matching=output,reference=anchor)
                    return result
            reference = load_tracking_snapshot(read_json(anchor),domain,base=anchor.parent)
            result = VacuumModeTracker(reference,domain,policy).evaluate(candidate,output)
        except Exception as error:
            result = {'status':'unconfirmed','reason':f'{type(error).__name__}: {error}',
                      'selected_modes':[],'physical_identity_confirmed':False,'solver_replayed':False}
            write_json_atomic(output,result)
        self.logger.info('模式匹配结束 | status=%s modes=%s reason=%s report=%s',
            result['status'],result.get('selected_modes',[]),result['reason'],output,
            extra={'event':'WORKER_VACUUM_MATCH','phase':'field-analysis',
                   'status':result['status'],'artifacts':{'matching':str(output)}})
        if getattr(self,'run_store',None) is not None and descriptor.get('snapshot_id'):
            self.run_store.artifacts(descriptor['snapshot_id'],mode_matching=output)
        return result

    def _stop_exit_is_confirmed(self) -> bool:
        """Exit 4 remains a task error; accept shutdown only with own saved recovery."""
        code = self._process.poll()
        if code == 0:
            return True
        if code != 4:
            return False
        project = getattr(self, 'project_path', None)
        if project is None:
            return False
        receipt = Path(str(project) + '.recovery-saved')
        snapshot = Path(str(project) + '.recovered.cst')
        try:
            valid = (receipt.read_text(encoding='ascii').splitlines()
                     == ['CST_RECOVERY_SAVED_V1', self.session_id]
                     and snapshot.is_file() and snapshot.stat().st_size > 0)
        except (OSError, UnicodeError):
            return False
        if valid:
            self.logger.warning('失败任务后已恢复快照并标准退出；保留CST退出码4 | WORKER_STOP_RECOVERED session=%s snapshot=%s',
                                self.session_id, snapshot,
                                extra={'event': 'WORKER_STOP_RECOVERED', 'phase': 'shutdown',
                                       'returncode': code, 'snapshot': snapshot})
        return valid

    def emergency_terminate(self) -> None:
        """Explicit last resort; callers must mark the project for recovery."""
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None:
                if os.name == "nt" and isinstance(getattr(process, "pid", None), int):
                    completed = subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    if completed.returncode != 0 and process.poll() is None:
                        process.kill()
                else:
                    process.kill()
                process.wait(timeout=30)
            self._close_log()

    def _close_log(self) -> None:
        progress_monitor = getattr(self, "_progress_monitor", None)
        if progress_monitor is not None:
            progress_monitor.stop()
        if self._log_stream is not None and not self._log_stream.closed:
            self._log_stream.close()
