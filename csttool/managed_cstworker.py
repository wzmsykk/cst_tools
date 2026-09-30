"""Production long-lived CST worker using the versioned file protocol."""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import Any, Mapping

from install_compat import resource_path

from .postprocess_cst import CstPostProcessor
from .cst_progress import CstLogProgressMonitor, CstLogProgressParser
from .vb_codec import quote_vb_string
from .logging_config import ContextLogger
from .worker_models import WorkerConfig, SimulationResult
from .diagnostics import write_run_manifest
from .runtime_protocol import (
    Acknowledge,
    CompletionStatus,
    FileProtocol,
    Task,
    atomic_publish,
    decode_completion,
    encode_ack,
    encode_task,
    new_session_id,
)


class ManagedWorkerShutdownError(RuntimeError):
    pass


class ManagedCSTWorker:
    START_TIMEOUT = 120.0
    TASK_TIMEOUT = 1200.0
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
        self._start()

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
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            **self._background_startup_options(),
        )
        self.pid_path.write_text(str(self._process.pid), encoding="ascii")
        if callable(self._progress_callback):
            parser = CstLogProgressParser(self.ID, self._progress_context)
            self._progress_monitor = CstLogProgressMonitor(
                self.log_path, parser, self._progress_callback
            )
            self._progress_monitor.start()
        self._wait_for_marker("ready", self.START_TIMEOUT)
        self.logger.info("CST 进程已启动 | worker=%s session=%s pid=%s project=%s", self.ID, self.session_id, self._process.pid, self.source_project)

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
            self.marker_path.write_text(
                f"dispatched:{task.task_id}", encoding="ascii"
            )
            atomic_publish(self.task_path, encode_task(task))
            try:
                completion = self._wait_completion(task)
            except Exception:
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
                try:
                    atomic_publish(
                        self.ack_path,
                        encode_ack(Acknowledge(task.task_id, task.session_id)),
                    )
                    self.logger.debug("任务 Ack 已发布 | TASK_ACK_PUBLISHED task=%s job=%s", task.task_id, result_name, extra={"event": "TASK_ACK_PUBLISHED", "phase": "ack", "task": task.task_id, "job": result_name})
                    self._wait_for_marker("ready", self.START_TIMEOUT)
                    self.logger.debug("CST 已回到就绪状态 | TASK_ACK_READY task=%s job=%s", task.task_id, result_name, extra={"event": "TASK_ACK_READY", "phase": "ack", "task": task.task_id, "job": result_name})
                except Exception:
                    self.logger.exception("任务确认阶段失败 | TASK_ACK_FAILED task=%s job=%s", task.task_id, result_name, extra={"event": "TASK_ACK_FAILED", "phase": "ack", "task": task.task_id, "job": result_name})
                    raise
                finally:
                    self._active_task_context = {}
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
            )

    @staticmethod
    def _progress_number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _wait_completion(self, task: Task):
        deadline = time.monotonic() + self.TASK_TIMEOUT
        while time.monotonic() < deadline:
            self._ensure_running()
            self._keep_window_minimized()
            if self.completion_path.exists():
                completion = decode_completion(
                    self.completion_path.read_text(encoding="utf-8")
                )
                if (completion.task_id, completion.session_id) != (
                    task.task_id,
                    task.session_id,
                ):
                    raise RuntimeError("completion belongs to another task")
                return completion
            time.sleep(0.1)
        raise TimeoutError(f"timed out waiting for CST task {task.task_id}")

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
            self.logger.error("CST 标准退出未获确认，需要会话恢复 | WORKER_STOP_FAILED worker=%s session=%s returncode=%s process_alive=%s timeout_seconds=%s", self.ID, self.session_id, self._process.poll(), self._process.poll() is None, self.STOP_TIMEOUT, extra={"event": "WORKER_STOP_FAILED", "phase": "shutdown", "worker": self.ID, "session": self.session_id, "returncode": self._process.poll(), "process_alive": self._process.poll() is None, "timeout_seconds": self.STOP_TIMEOUT})
            raise ManagedWorkerShutdownError(
                f"worker {self.ID} did not confirm standard Save/Quit; "
                "explicit emergency termination is required"
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
