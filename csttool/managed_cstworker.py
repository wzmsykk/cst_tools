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
from .configuration import write_json_atomic
from .cst_progress import CstLogProgressMonitor, CstLogProgressParser
from .vb_codec import quote_vb_string
from .logging_config import ContextLogger
from .worker_models import WorkerConfig, SimulationResult
from .cst_process_env import cst_process_environment
from .resource_usage import record_worker_usage
from .native_progress import NativeProgressTracker
from .solver_output import SolverOutputTracker
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
        self.result_root = config.result_directory.resolve() / f"worker_{worker_id}"
        self.source_project = config.project_path.resolve()
        self.executable = config.executable.resolve()
        self.parameter_definitions = tuple(config.parameters)
        self.postprocess = CstPostProcessor()
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
        self.log_path = self.root / "cst.log"
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
        self.result_root.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "cst_log": self.log_path, "macro": self.macro_path,
            "project": self.project_path, "task": self.task_path,
            "completion": self.completion_path, "ack": self.ack_path,
            "state": self.marker_path, "stop_request": self.stop_request_path,
            "stop_ack": self.stop_ack_path, "results": self.result_root,
        }
        manifest = write_run_manifest(self.root / "diagnostics.json", config, artifacts,
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
            path = write_failure_report(self.root, phase=phase,
                process=getattr(self, '_process', None),
                context={"worker": self.ID, "session": self.session_id,
                         **getattr(self, '_active_task_context', {})},
                paths={name: getattr(self, name, None) for name in (
                    'log_path', 'marker_path', 'task_path', 'completion_path',
                    'ack_path', 'stop_request_path', 'stop_ack_path')} | {
                        'lifecycle_log': Path(str(self.marker_path) + '.lifecycle.log'),
                        'received_receipt': self.root / 'received' / (
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
            "%STOP_REQUEST_PATH%": quote_vb_string(self.stop_request_path),
            "%STOP_ACK_PATH%": quote_vb_string(self.stop_ack_path),
            "%RESULT_ROOT%": quote_vb_string(str(self.result_root) + "\\"),
        }
        for placeholder, value in replacements.items():
            main = main.replace(placeholder, value)
        generated = "".join(self.postprocess.render_vb())
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

    def _start(self) -> None:
        self._log_stream = self.log_path.open("wb", buffering=0)
        self._process = subprocess.Popen(
            [str(self.executable), "-m", str(self.macro_path)],
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
            if getattr(self, '_resource_usage', None) is not None:
                self._resource_usage.identity['task_id'] = task.task_id
            self._active_task_context = {
                "task_id": task.task_id,
                "interval_lo": self._progress_number(params.get("fmin")),
                "interval_hi": self._progress_number(params.get("fmax")),
            }
            started_at = time.monotonic()
            self.logger.info(
                "任务已发送给 CST | WORKER_TASK_DISPATCH worker=%s session=%s task=%s job=%s fmin=%s fmax=%s",
                self.ID,
                self.session_id,
                task.task_id,
                result_name,
                params.get("fmin"),
                params.get("fmax"), extra={"event": "WORKER_TASK_DISPATCH", "phase": "solve", "worker": self.ID, "session": self.session_id, "task": task.task_id, "job": result_name, "fmin": params.get("fmin"), "fmax": params.get("fmax")})
            self._native_progress = NativeProgressTracker(
                self.project_path.with_suffix('') / 'Result' / 'progress.log',
                self.root / 'native_progress' / task.task_id,
                self.ID, self.session_id, task, self.logger,
                getattr(self, '_progress_callback', None),
            )
            self._solver_output = SolverOutputTracker(
                self.project_path.with_suffix('') / 'Result' / 'output.txt',
                self.root / 'native_progress' / task.task_id, task, self.logger,
            )
            self.marker_path.write_text(
                f"dispatched:{task.task_id}", encoding="ascii"
            )
            atomic_publish(self.task_path, payload)
            try:
                completion = self._wait_completion(task)
            except Exception:
                self._diagnose_failure("completion")
                self.logger.exception("等待 CST 完成失败 | CST_COMPLETION_FAILED task=%s job=%s", task.task_id, result_name, extra={"event": "CST_COMPLETION_FAILED", "phase": "solve", "task": task.task_id, "job": result_name})
                self._active_task_context = {}
                raise
            self.logger.debug("收到 CST 完成标记 | CST_COMPLETION task=%s job=%s status=%s", task.task_id, result_name, completion.status.value, extra={"event": "CST_COMPLETION", "phase": "solve", "task": task.task_id, "job": result_name, "status": completion.status.value})
            task_result_root = self.result_root / task.task_id
            project_snapshot = task_result_root / "project.cst"
            try:
                if completion.status is CompletionStatus.SUCCESS:
                    if not project_snapshot.is_file() or project_snapshot.stat().st_size == 0:
                        raise FileNotFoundError(
                            f"CST task did not publish a project snapshot: {project_snapshot}"
                        )
                    self.postprocess.set_result_directory(task_result_root)
                    self.postprocess.set_cst_run_result_directory(task_result_root / "project")
                    postprocess_result = self.postprocess.read_all_results()
                    self.logger.debug("后处理结果读取完成 | RESULT_READ_DONE task=%s job=%s results=%d snapshot=%s", task.task_id, result_name, len(postprocess_result), project_snapshot, extra={"event": "RESULT_READ_DONE", "phase": "readout", "task": task.task_id, "job": result_name, "results": len(postprocess_result), "snapshot": project_snapshot})
                    status = "Success"
                    failure = None
                else:
                    postprocess_result = None
                    status = "Failure"
                    failure = f"{completion.error_code.value}: {completion.error_message}"
            except Exception as exc:
                self.logger.exception("后处理结果读取失败 | RESULT_READ_FAILED task=%s job=%s", task.task_id, result_name, extra={"event": "RESULT_READ_FAILED", "phase": "readout", "task": task.task_id, "job": result_name})
                postprocess_result = None
                status = "Failure"
                failure = f"RESULT_READ_FAILED: {type(exc).__name__}: {exc}"
            finally:
                receipt_path = self.root / 'received' / f'{task.task_id}.json'
                received = {
                    'schema_version': 1, 'phase': 'received',
                    'task_id': task.task_id, 'session_id': task.session_id,
                    'job': result_name, 'parameters': dict(params),
                    'status': status, 'failure': failure, 'postprocess': postprocess_result,
                    'snapshot': str(project_snapshot.resolve()) if project_snapshot.exists() else None,
                }
                try:
                    # Persist result consumption BEFORE authorizing VBA cleanup.
                    write_json_atomic(receipt_path, received)
                    publish_ack_idempotently(
                        self.ack_path,
                        Acknowledge(task.task_id, task.session_id),
                    )
                    self.logger.debug("任务 Ack 已发布 | TASK_ACK_PUBLISHED task=%s job=%s", task.task_id, result_name, extra={"event": "TASK_ACK_PUBLISHED", "phase": "ack", "task": task.task_id, "job": result_name})
                    self._wait_for_marker("ready", self.START_TIMEOUT)
                    write_json_atomic(receipt_path, {**received, 'phase': 'acknowledged'})
                    self.logger.debug("CST 已回到就绪状态 | TASK_ACK_READY task=%s job=%s", task.task_id, result_name, extra={"event": "TASK_ACK_READY", "phase": "ack", "task": task.task_id, "job": result_name})
                except Exception as exc:
                    self._diagnose_failure("ack")
                    self.logger.exception("任务确认阶段失败 | TASK_ACK_FAILED task=%s job=%s", task.task_id, result_name, extra={"event": "TASK_ACK_FAILED", "phase": "ack", "task": task.task_id, "job": result_name})
                    raise ManagedAcknowledgmentPending(receipt_path, exc) from exc
                finally:
                    self._active_task_context = {}
            if status == "Success":
                task_result_root, project_snapshot = self._name_result_archive(
                    task, result_name, task_result_root, postprocess_result
                )
                self.postprocess.set_result_directory(task_result_root)
                self.postprocess.set_cst_run_result_directory(project_snapshot.with_suffix(""))
                try:
                    write_json_atomic(receipt_path, {**received, 'phase': 'acknowledged',
                                                   'snapshot': str(project_snapshot.resolve())})
                except OSError:
                    self.logger.warning('接收记录存档路径更新失败，原始记录仍保留', exc_info=True)
            log_method = self.logger.info if status == "Success" else self.logger.error
            log_method(
                "CST 任务结束 | WORKER_TASK_COMPLETE worker=%s task=%s status=%s elapsed_seconds=%.3f failure=%s job=%s",
                self.ID,
                task.task_id,
                status,
                time.monotonic() - started_at,
                failure or "none",
                result_name, extra={"event": "WORKER_TASK_COMPLETE", "phase": "solve", "worker": self.ID, "task": task.task_id, "status": status, "elapsed_seconds": time.monotonic() - started_at, "failure": failure or "none", "job": result_name})
            return SimulationResult(
                self.ID, status, result_name, dict(params), postprocess_result,
                failure, project_snapshot.resolve() if status == "Success" else None,
                task_id=task.task_id, result_directory=task_result_root.resolve(),
            )

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
                    "CST 仍在运行 | task=%s elapsed_seconds=%.1f log_bytes=%s", task.task_id, elapsed, log_size,
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

    def stop(self) -> bool:
        with self._lock:
            if self._process is None:
                return True
            if self._process.poll() is not None:
                self.logger.debug("CST 进程已结束，无需重复退出 | WORKER_ALREADY_EXITED worker=%s session=%s returncode=%s", self.ID, self.session_id, self._process.poll(), extra={"event": "WORKER_ALREADY_EXITED", "phase": "readout", "worker": self.ID, "session": self.session_id, "returncode": self._process.poll()})
                self._close_log()
                return True
            self._stopping = True
            self.logger.info(
                "请求 CST 标准退出 | WORKER_STOP_REQUEST worker=%s session=%s pid=%s",
                self.ID,
                self.session_id,
                getattr(self._process, "pid", None), extra={"event": "WORKER_STOP_REQUEST", "phase": "shutdown", "worker": self.ID, "session": self.session_id, "pid": getattr(self._process, "pid", None)})
            if not self.stop_request_path.exists():
                self.protocol.request_stop(self.session_id)
            deadline = time.monotonic() + self.STOP_TIMEOUT
            while time.monotonic() < deadline:
                if self.protocol.read_stop_ack(self.session_id) is not None:
                    try:
                        self._process.wait(timeout=max(0.1, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        break
                    self._close_log()
                    self.logger.info(
                        "CST 已确认停止并退出 | WORKER_STOPPED worker=%s session=%s", self.ID, self.session_id, extra={"event": "WORKER_STOPPED", "phase": "shutdown", "worker": self.ID, "session": self.session_id})
                    return True
                if self._process.poll() is not None:
                    break
                time.sleep(0.1)

            if self._process.poll() is not None:
                self._close_log()
            self._diagnose_failure("shutdown")
            self.logger.error("CST 标准退出未获确认，需要会话恢复 | WORKER_STOP_FAILED worker=%s session=%s returncode=%s process_alive=%s timeout_seconds=%s", self.ID, self.session_id, self._process.poll(), self._process.poll() is None, self.STOP_TIMEOUT, extra={"event": "WORKER_STOP_FAILED", "phase": "shutdown", "worker": self.ID, "session": self.session_id, "returncode": self._process.poll(), "process_alive": self._process.poll() is None, "timeout_seconds": self.STOP_TIMEOUT})
            raise ManagedWorkerShutdownError(
                f"worker {self.ID} did not confirm standard Save/Quit; " + (
                    "process already exited; reconcile preserved protocol and snapshot"
                    if self._process.poll() is not None else
                    "process is still running; session recovery is required"
                )
            )

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
