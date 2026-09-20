import json
import time
from pathlib import Path

import pytest

from csttool.managed_cstworker import ManagedCSTWorker
from csttool.project_session_recovery import (
    discover_managed_sessions,
    recover_project_sessions,
)
from csttool.runtime_protocol import Task, atomic_publish, encode_task
from test.cst_integration_support import (
    cst_processes,
    force_cleanup,
    windows_process_snapshot,
)


pytestmark = pytest.mark.integration


def _config(project: Path, cst_executable: Path) -> dict:
    source = Path(__file__).parent / "data" / "Pillbox" / "Pillbox.cst"
    return {
        "taskFileDir": str(project / "temp" / "worker_0"),
        "resultDir": str(project / "result"),
        "cstPath": str(source),
        "CSTENVPATH": str(cst_executable),
        "runInBackground": True,
        "paramList": [
            {"name": "nmodes", "type": "double"},
            {"name": "fmin", "type": "double"},
            {"name": "fmax", "type": "double"},
        ],
        "postProcess": [
            {
                "resultName": "frequency",
                "method": "Frequency",
                "params": {"iModeNumber": 1},
            }
        ],
    }


def _dispatch_without_controller(worker: ManagedCSTWorker) -> Task:
    task = Task.create(
        worker.session_id,
        {"nmodes": 1, "fmin": 400, "fmax": 1200},
    )
    worker.marker_path.write_text(f"dispatched:{task.task_id}", encoding="ascii")
    atomic_publish(worker.task_path, encode_task(task))
    return task


def _wait_until_solver_started(worker: ManagedCSTWorker, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if worker._process.poll() is not None:
            pytest.fail(f"CST exited before fault injection: {worker._process.returncode}")
        text = worker.log_path.read_text(encoding="utf-8", errors="replace")
        if "Eigenmode" in text or "Mesh" in text:
            return
        time.sleep(0.1)
    pytest.fail("CST did not enter mesh/solver stage before fault injection")


def test_controller_loss_is_recovered_through_standard_protocol(
    cst_executable, tmp_path
):
    project = tmp_path / "controller-loss"
    baseline = cst_processes(windows_process_snapshot())
    worker = None
    forced_cleanup = {}
    try:
        worker = ManagedCSTWorker("0", _config(project, cst_executable))
        task = _dispatch_without_controller(worker)
        _wait_until_solver_started(worker)

        recovered = recover_project_sessions(project, timeout_per_session=300)

        assert [item.session_id for item in recovered] == [worker.session_id]
        receipt = json.loads(
            (worker.root / "recovery.json").read_text(encoding="utf-8")
        )
        assert receipt["disposition"] == "standard-stop"
        assert receipt["completion_task_id"] == task.task_id
        assert worker.protocol.read_stop_ack(worker.session_id) is not None
        assert worker._process.poll() == 0
        assert not [
            item for item in discover_managed_sessions(project) if item.needs_recovery
        ]
        worker._close_log()
    finally:
        process = worker._process if worker is not None else None
        forced_cleanup = force_cleanup(process, baseline)

    assert not forced_cleanup, f"controller-loss recovery leaked CST: {forced_cleanup}"


def test_dead_cst_is_abandoned_without_forging_standard_exit(
    cst_executable, tmp_path
):
    project = tmp_path / "dead-cst"
    baseline = cst_processes(windows_process_snapshot())
    worker = None
    forced_cleanup = {}
    try:
        worker = ManagedCSTWorker("0", _config(project, cst_executable))
        _dispatch_without_controller(worker)
        _wait_until_solver_started(worker)
        injected_pid = worker._process.pid

        worker.emergency_terminate()
        assert worker._process.pid == injected_pid
        assert worker._process.poll() is not None
        assert worker.protocol.read_stop_ack(worker.session_id) is None

        recovered = recover_project_sessions(project, timeout_per_session=30)

        assert [item.session_id for item in recovered] == [worker.session_id]
        receipt = json.loads(
            (worker.root / "recovery.json").read_text(encoding="utf-8")
        )
        assert receipt["disposition"] == "abandoned-dead"
        assert worker.protocol.read_stop_ack(worker.session_id) is None
        assert worker.marker_path.read_text(encoding="ascii") == "abandoned-dead"
        assert not [
            item for item in discover_managed_sessions(project) if item.needs_recovery
        ]
    finally:
        process = worker._process if worker is not None else None
        forced_cleanup = force_cleanup(process, baseline)

    assert not forced_cleanup, f"dead-CST recovery leaked child processes: {forced_cleanup}"
