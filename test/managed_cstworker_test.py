import logging

import pytest

from csttool.cstmanager import CSTManager, ManagerState
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.postprocess_cst import VBPostProcessor


def build_worker_shell(tmp_path):
    worker = object.__new__(ManagedCSTWorker)
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
        self.conf = {
            "BASE": {"datadir": str(root / "data")},
            "CST": {"cstexepath": str(root / "cst.exe")},
        }


class _Project:
    def __init__(self, root):
        self.currProjectDir = root
        self.conf = {
            "DIRS": {"tempdir": "temp", "resultdir": "result"},
            "CST": {"CSTFilename": "model.cst"},
            "PROJECT": {"ProjectType": "default"},
        }

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
