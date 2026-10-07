import logging
import os
import threading
import json
from pathlib import Path

import pytest

from csttool.configuration import CstBackendSettings, GlobalSettings, ProjectSettings
from csttool.cstmanager import CSTManager, ManagerState
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.managed_cstworker import ManagedWorkerShutdownError
from csttool.postprocess_cst import VBPostProcessor
from csttool.runtime_protocol import Task
from csttool.runtime_protocol import Completion, CompletionStatus


def build_worker_shell(tmp_path):
    worker = object.__new__(ManagedCSTWorker)
    worker.logger = logging.getLogger("managed-worker-test")
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
    worker.postprocess = VBPostProcessor()
    worker.postprocess.appendPostProcessSteps(
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


def test_named_result_archive_preserves_cst_companion_and_task_identity(tmp_path):
    worker = build_worker_shell(tmp_path)
    task = Task.create(worker.session_id, {"fmin": 700, "fmax": 800})
    directory = worker.result_root / task.task_id
    directory.mkdir(parents=True)
    (directory / "project.cst").write_bytes(b"snapshot")
    (directory / "project" / "Result").mkdir(parents=True)
    (directory / "project" / "Result" / "field.rd0").write_bytes(b"field-data")
    postprocess = [{"resultName": "frequency", "value": 721.049793675422}]

    result_dir, snapshot = worker._name_result_archive(task, "hom_700_800", directory, postprocess)

    assert result_dir.name == f"hom_700_800__f_721.049794MHz__{task.task_id}"
    assert snapshot.name == "hom_700_800__f_721.049794MHz.cst"
    assert snapshot.read_bytes() == b"snapshot"
    assert (snapshot.with_suffix("") / "Result" / "field.rd0").read_bytes() == b"field-data"
    assert not directory.exists()
    metadata = json.loads((result_dir / "task_result.json").read_text(encoding="utf-8"))
    assert metadata["taskId"] == task.task_id
    assert metadata["projectSnapshot"] == snapshot.name
    assert metadata["postprocess"] == postprocess


def test_named_archive_keeps_original_on_destination_collision(tmp_path):
    worker = build_worker_shell(tmp_path)
    task = Task.create(worker.session_id, {})
    directory = worker.result_root / task.task_id
    directory.mkdir(parents=True)
    (directory / "project.cst").write_bytes(b"snapshot")
    (directory / "project").mkdir()
    destination = worker.result_root / f"task__{task.task_id}"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep", encoding="utf-8")

    result_dir, snapshot = worker._name_result_archive(task, "task", directory, [])
    assert result_dir == directory
    assert snapshot.name == "project.cst"
    assert snapshot.read_bytes() == b"snapshot"
    assert (directory / "project").is_dir()
    assert (destination / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_archive_name_cannot_escape_result_root(tmp_path):
    worker = build_worker_shell(tmp_path)
    task = Task.create(worker.session_id, {})
    directory = worker.result_root / task.task_id
    directory.mkdir(parents=True)
    (directory / "project.cst").write_bytes(b"snapshot")
    result_dir, snapshot = worker._name_result_archive(task, '../bad:name\\file', directory, [])
    assert result_dir.parent == worker.result_root
    assert snapshot.parent == result_dir
    assert snapshot.is_file()


def test_worker_names_archive_only_after_acknowledgement(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker.ID = "0"
    worker._lock = threading.RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    observed = []
    sample = [{"resultName": "frequency", "value": 721.049793675422}]

    def wait_completion(task):
        directory = worker.result_root / task.task_id
        directory.mkdir(parents=True)
        (directory / "project.cst").write_bytes(b"confirmed-snapshot")
        (directory / "project").mkdir()
        observed.append(directory)
        return Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS)

    def wait_ready(marker, timeout):
        if observed:
            assert worker.ack_path.exists()
            assert (observed[0] / "project.cst").is_file()

    monkeypatch.setattr(worker, "_wait_completion", wait_completion)
    monkeypatch.setattr(worker, "_wait_for_marker", wait_ready)
    monkeypatch.setattr(worker.postprocess, "readAllResults", lambda: sample)
    result = worker.runWithParam("hom_700_800", params={"fmin": 700, "fmax": 800})
    assert result["TaskStatus"] == "Success"
    snapshot = Path(result["ProjectSnapshot"])
    assert snapshot.is_file()
    assert snapshot.parent == Path(result["ResultDirectory"])
    assert result["TaskID"] in snapshot.parent.name
    assert not observed[0].exists()


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


def test_standard_stop_timeout_does_not_kill_cst(tmp_path):
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
        worker.runWithParam("task", params={"x": 1})

    assert observed[0].startswith("dispatched:")


class _Global:
    def __init__(self, root):
        self.settings = GlobalSettings(cst=CstBackendSettings(executable=root / "cst.exe"))


class _Project:
    def __init__(self, root):
        self.currProjectDir = root
        self.settings = ProjectSettings(name="default", cst_filename=Path("model.cst"))

    def getCurrPPSList(self):
        return []


class _BadStopWorker:
    def runWithParam(self, resultname, *, params):
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
