import logging
from pathlib import Path
import os
import threading

import pytest

from csttool.cstmanager import CSTManager, ManagerState
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.managed_cstworker import ManagedWorkerShutdownError
from csttool.postprocess_cst import CstPostProcessor


def build_worker_shell(tmp_path):
    worker = object.__new__(ManagedCSTWorker)
    worker.logger = logging.getLogger("managed-worker-test")
    worker.root = tmp_path
    worker.project_path = tmp_path / "worker-input.cst"
    worker.session_id = "11111111-1111-4111-8111-111111111111"
    worker.task_path = tmp_path / "protocol" / "current.task"
    worker.completion_path = tmp_path / "protocol" / "current.completion"
    worker.ack_path = tmp_path / "protocol" / "current.ack"
    worker.marker_path = tmp_path / "worker.state"
    worker.stop_request_path = tmp_path / "protocol" / "stop.request"
    worker.stop_ack_path = tmp_path / "protocol" / "stop.ack"
    worker.result_root = tmp_path / "results"
    worker.macro_path = tmp_path / "runtime_managed_worker_v1.bas"
    worker.postprocess = CstPostProcessor()
    worker.postprocess.configure(
        [
            {
                "resultName": "frequency",
                "method": "Frequency",
                "params": {"iModeNumber": 1},
            },
            {
                "resultName": "rq",
                "method": "R_over_Q",
                "params": {
                    "iModeNumber": 1,
                    "axis": "x",
                    "xoffset": 0,
                    "yoffset": 2,
                    "zoffset": 3,
                },
            },
        ]
    )
    return worker


def test_archive_failure_does_not_dispatch_task(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker._lock = threading.RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    worker.marker_path.write_text('ready', encoding='ascii')
    monkeypatch.setattr(worker, '_wait_for_marker', lambda *args: None)
    def fail_archive(*args):
        raise OSError('archive unavailable')
    monkeypatch.setattr('csttool.managed_cstworker.archive_task', fail_archive)
    with pytest.raises(OSError, match='archive unavailable'):
        worker.run_task('mode-1', params={})
    assert worker.marker_path.read_text(encoding='ascii') == 'ready'
    assert not worker.task_path.exists()


def test_managed_worker_macro_is_dynamic_ack_gated_and_standard_exit(tmp_path):
    worker = build_worker_shell(tmp_path)

    worker._build_macro()

    macro = worker.macro_path.read_text(encoding="ascii")
    assert macro.lower().count("sub main") == 1
    assert "current.task" in macro
    assert "CSTP_ReadTask" in macro
    assert "CSTP_ReadAck" in macro
    assert "CSTP_ReadStopRequest" in macro
    assert "Do\n" in macro
    assert "Save\n            Quit" in macro
    assert "stopped-with-completion" in macro
    assert "EigenResult_Simple_output" in macro
    assert "EigenResult_Complex_output" in macro
    assert "%" not in macro


def test_expression_kind_comes_from_parameter_metadata_or_runtime_value():
    worker = object.__new__(ManagedCSTWorker)
    worker.parameter_definitions = (
        {"name": "literal", "type": "double"},
        {"name": "expr", "type": "expression"},
    )

    names = worker._expression_names(
        {"literal": 2.5, "expr": "2 * literal", "dynamic": "literal + 1"}
    )

    assert names == frozenset({"expr", "dynamic"})


def test_managed_worker_uses_non_activating_minimized_startup_on_windows():
    worker = object.__new__(ManagedCSTWorker)
    worker._run_in_background = True

    options = worker._background_startup_options()

    if os.name == "nt":
        startupinfo = options["startupinfo"]
        assert startupinfo.dwFlags & __import__("subprocess").STARTF_USESHOWWINDOW
        assert startupinfo.wShowWindow == 7
        assert options["creationflags"] & __import__(
            "subprocess"
        ).CREATE_NEW_PROCESS_GROUP
    else:
        assert options == {}


def test_managed_worker_can_leave_cst_window_interactive():
    worker = object.__new__(ManagedCSTWorker)
    worker._run_in_background = False

    options = worker._background_startup_options()
    if os.name == "nt":
        assert "startupinfo" not in options
        assert options["creationflags"] & __import__(
            "subprocess"
        ).CREATE_NEW_PROCESS_GROUP
    else:
        assert options == {}


def test_standard_stop_timeout_does_not_kill_cst(tmp_path, caplog):
    class Process:
        pid = 1

        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    worker = build_worker_shell(tmp_path)
    worker.ID = "test"
    worker._lock = threading.RLock()
    worker._process = Process()
    worker._stopping = False
    worker.STOP_TIMEOUT = 0.01
    worker.protocol = __import__(
        "csttool.runtime_protocol", fromlist=["FileProtocol"]
    ).FileProtocol(tmp_path / "protocol")

    with pytest.raises(ManagedWorkerShutdownError, match="emergency termination"):
        worker.stop()

    assert not worker._process.killed
    assert "WORKER_STOP_FAILED" in caplog.text
    assert "WORKER_STOPPED" not in caplog.text


@pytest.mark.parametrize("ack_fails", [False, True])
def test_task_logs_results_before_ack_and_only_completes_after_ready(tmp_path, monkeypatch, caplog, ack_fails):
    from types import SimpleNamespace
    from csttool.runtime_protocol import CompletionStatus

    worker = build_worker_shell(tmp_path)
    worker.ID = "test"
    worker._lock = threading.RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    worker.TASK_TIMEOUT = 1
    calls = []

    def wait_marker(*args):
        calls.append(args)
        if ack_fails and len(calls) == 2:
            raise TimeoutError("ready timeout")

    def complete(task):
        snapshot = worker.result_root / task.task_id / "project.cst"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes(b"snapshot")
        return SimpleNamespace(status=CompletionStatus.SUCCESS)

    monkeypatch.setattr(worker, "_wait_for_marker", wait_marker)
    monkeypatch.setattr(worker, "_wait_completion", complete)
    monkeypatch.setattr(worker.postprocess, "read_all_results", lambda: [])
    caplog.set_level(logging.DEBUG)
    if ack_fails:
        with pytest.raises(TimeoutError):
            worker.run_task("mode-1", params={})
        assert "TASK_ACK_FAILED" in caplog.text
        assert "WORKER_TASK_COMPLETE" not in caplog.text
    else:
        worker.run_task("mode-1", params={})
        events = ["CST_COMPLETION ", "RESULT_READ_DONE", "TASK_ACK_PUBLISHED", "TASK_ACK_READY", "WORKER_TASK_COMPLETE"]
        offsets = [caplog.text.index(event) for event in events]
        assert offsets == sorted(offsets)
    assert worker._active_task_context == {}


def test_emergency_termination_is_explicit(tmp_path):
    class Process:
        def __init__(self):
            self.killed = False

        def poll(self):
            return None if not self.killed else 1

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            return 1

    worker = build_worker_shell(tmp_path)
    worker._lock = threading.RLock()
    worker._process = Process()
    worker._log_stream = None

    worker.emergency_terminate()

    assert worker._process.killed


def test_ready_marker_is_invalidated_before_task_publication(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker.ID = "test"
    worker._lock = __import__("threading").RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    worker.session_id = "11111111-1111-4111-8111-111111111111"
    worker.marker_path.write_text("ready", encoding="ascii")
    observed = []

    monkeypatch.setattr(worker, "_wait_for_marker", lambda expected, timeout: None)
    monkeypatch.setattr(
        "csttool.managed_cstworker.atomic_publish",
        lambda path, text: observed.append(worker.marker_path.read_text(encoding="ascii")),
    )
    monkeypatch.setattr(worker, "_wait_completion", lambda task: (_ for _ in ()).throw(RuntimeError("stop")))

    with pytest.raises(RuntimeError, match="stop"):
        worker.run_task("task", params={"x": 1})

    assert observed[0].startswith("dispatched:")


class _Global:
    def __init__(self, root):
        self.settings = GlobalSettings().with_cst("2022", str(root / "cst.exe"))


class _Project:
    def __init__(self, root):
        self.currProjectDir = root
        self.settings = ProjectSettings(name="test-project", cst_filename=Path("model.cst"))

    def get_postprocess_settings(self):
        return []


class _BadStopWorker:
    def run_task(self, resultname, *, params):
        raise AssertionError("not used")

    def stop(self):
        raise RuntimeError("standard shutdown failed")


def test_manager_propagates_worker_shutdown_failure_after_closing(tmp_path):
    manager = CSTManager(
        _Global(tmp_path),
        _Project(tmp_path),
        params=[],
        logger=logging.getLogger("managed-worker-stop-test"),
        maxTask=1,
        worker_factory=lambda *_args: _BadStopWorker(),
    )

    with pytest.raises(RuntimeError, match="did not stop cleanly"):
        manager.stop()

    assert manager.state is ManagerState.CLOSED
from csttool.configuration import GlobalSettings, ProjectSettings
