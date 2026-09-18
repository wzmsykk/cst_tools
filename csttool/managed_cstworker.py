"""Production long-lived CST worker using the versioned file protocol."""

from __future__ import annotations

import logging
import math
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import Any, Mapping

from install_compat import resource_path

from .postprocess_cst import VBPostProcessor
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
        self._lock = threading.RLock()
        self._stopping = False
        self._process: subprocess.Popen | None = None
        self._log_stream = None

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
        )
        self._wait_for_marker("ready", self.START_TIMEOUT)
        self.logger.info("Managed CST worker %s started pid=%s", self.ID, self._process.pid)

    def _wait_for_marker(self, expected: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._ensure_running()
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
            self.marker_path.write_text(
                f"dispatched:{task.task_id}", encoding="ascii"
            )
            atomic_publish(self.task_path, encode_task(task))
            completion = self._wait_completion(task)
            task_result_root = self.result_root / task.task_id
            try:
                if completion.status is CompletionStatus.SUCCESS:
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
            return {
                "WorkerID": self.ID,
                "TaskStatus": status,
                "FailureReport": failure,
                "RunName": resultname,
                "RunParameters": dict(params),
                "PostProcessResult": postprocess_result,
            }

    def _wait_completion(self, task: Task):
        deadline = time.monotonic() + self.TASK_TIMEOUT
        while time.monotonic() < deadline:
            self._ensure_running()
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
                    return True
                if self._process.poll() is not None:
                    break
                time.sleep(0.1)

            process = self._process
            if process.poll() is None:
                process.kill()
                process.wait(timeout=30)
            self._close_log()
            raise ManagedWorkerShutdownError(
                f"worker {self.ID} required forced termination; standard Save/Quit failed"
            )

    def _close_log(self) -> None:
        if self._log_stream is not None and not self._log_stream.closed:
            self._log_stream.close()
