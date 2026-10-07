"""Production long-lived CST worker using the versioned file protocol."""

from __future__ import annotations

import logging
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

from .postprocess_cst import VBPostProcessor
from .configuration import write_json_atomic
from .cst_progress import CstLogProgressMonitor, CstLogProgressParser
from .protocol_worker import _vb_string
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

    def __init__(self, worker_id: str, config: Mapping[str, Any], logger=None):
        self.ID = worker_id
        self.logger = logger or logging.getLogger(__name__)
        worker_root = Path(config["taskFileDir"]).resolve()
        self.session_id = new_session_id()
        self.root = worker_root / self.session_id
        self.result_root = Path(config["resultDir"]).resolve() / f"worker_{worker_id}"
        self.source_project = Path(config["cstPath"]).resolve()
        self.executable = Path(config["CSTENVPATH"]).resolve()
        self.parameter_definitions = tuple(config["paramList"])
        self.postprocess = VBPostProcessor()
        self.postprocess.appendPostProcessSteps(config.get("postProcess", ()))
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
        self._run_in_background = bool(config.get("runInBackground", True))
        self._last_window_check = 0.0
        self._progress_callback = config.get("progressCallback")
        self._active_task_context: dict[str, Any] = {}
        self._progress_monitor: CstLogProgressMonitor | None = None

        self.root.mkdir(parents=True, exist_ok=True)
        self.result_root.mkdir(parents=True, exist_ok=True)
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
            "%PROJECT_PATH%": _vb_string(self.project_path),
            "%SESSION_ID%": self.session_id,
            "%TASK_PATH%": _vb_string(self.task_path),
            "%COMPLETION_PATH%": _vb_string(self.completion_path),
            "%ACK_PATH%": _vb_string(self.ack_path),
            "%MARKER_PATH%": _vb_string(self.marker_path),
            "%STOP_REQUEST_PATH%": _vb_string(self.stop_request_path),
            "%STOP_ACK_PATH%": _vb_string(self.stop_ack_path),
            "%RESULT_ROOT%": _vb_string(str(self.result_root) + "\\"),
        }
        for placeholder, value in replacements.items():
            main = main.replace(placeholder, value)
        generated = "".join(self.postprocess.createPostProcessVBCodeLines())
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
        self.logger.info("Managed CST worker %s started pid=%s", self.ID, self._process.pid)

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

    def runWithParam(self, resultname: str, *, params: Mapping[str, Any]) -> dict:
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
                "WORKER_TASK_DISPATCH worker=%s session=%s task=%s job=%s fmin=%s fmax=%s",
                self.ID,
                self.session_id,
                task.task_id,
                resultname,
                params.get("fmin"),
                params.get("fmax"),
            )
            self.marker_path.write_text(
                f"dispatched:{task.task_id}", encoding="ascii"
            )
            atomic_publish(self.task_path, encode_task(task))
            completion = self._wait_completion(task)
            task_result_root = self.result_root / task.task_id
            project_snapshot = task_result_root / "project.cst"
            try:
                if completion.status is CompletionStatus.SUCCESS:
                    if not project_snapshot.is_file() or project_snapshot.stat().st_size == 0:
                        raise FileNotFoundError(
                            f"CST task did not publish a project snapshot: {project_snapshot}"
                        )
                    self.postprocess.setResultDir(task_result_root)
                    self.postprocess.setCSTRunResultDir(task_result_root / "project")
                    postprocess_result = self.postprocess.readAllResults()
                    status = "Success"
                    failure = None
                else:
                    postprocess_result = None
                    status = "Failure"
                    failure = f"{completion.error_code.value}: {completion.error_message}"
            except Exception as exc:
                postprocess_result = None
                status = "Failure"
                failure = f"RESULT_READ_FAILED: {type(exc).__name__}: {exc}"
            finally:
                atomic_publish(
                    self.ack_path,
                    encode_ack(Acknowledge(task.task_id, task.session_id)),
                )
                self._wait_for_marker("ready", self.START_TIMEOUT)
                self._active_task_context = {}
            if status == "Success":
                task_result_root, project_snapshot = self._name_result_archive(
                    task, resultname, task_result_root, postprocess_result
                )
                self.postprocess.setResultDir(task_result_root)
                self.postprocess.setCSTRunResultDir(project_snapshot.with_suffix(""))
            log_method = self.logger.info if status == "Success" else self.logger.error
            log_method(
                "WORKER_TASK_COMPLETE worker=%s task=%s status=%s elapsed_seconds=%.3f failure=%s",
                self.ID,
                task.task_id,
                status,
                time.monotonic() - started_at,
                failure or "none",
            )
            return {
                "WorkerID": self.ID,
                "TaskStatus": status,
                "FailureReport": failure,
                "RunName": resultname,
                "RunParameters": dict(params),
                "TaskID": task.task_id,
                "ResultDirectory": str(task_result_root.resolve()),
                "PostProcessResult": postprocess_result,
                "ProjectSnapshot": (
                    str(project_snapshot.resolve()) if status == "Success" else None
                ),
            }

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
                self._close_log()
                return True
            self._stopping = True
            self.logger.info(
                "WORKER_STOP_REQUEST worker=%s session=%s pid=%s",
                self.ID,
                self.session_id,
                getattr(self._process, "pid", None),
            )
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
                        "WORKER_STOPPED worker=%s session=%s", self.ID, self.session_id
                    )
                    return True
                if self._process.poll() is not None:
                    break
                time.sleep(0.1)

            if self._process.poll() is not None:
                self._close_log()
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
