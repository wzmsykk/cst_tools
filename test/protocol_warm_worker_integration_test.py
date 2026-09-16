import math
import subprocess
import time
from pathlib import Path

import pytest

from csttool.postprocess_cst import VBPostProcessor
from csttool.protocol_warm_worker import prepare_warm_worker_workspace
from csttool.runtime_protocol import CompletionStatus, Task, new_session_id
from test.cst_integration_support import (
    cst_processes, force_cleanup, wait_completion_or_controller_exit,
    wait_for_standard_exit, windows_process_snapshot,
)


pytestmark = pytest.mark.integration


def _wait_until(predicate, process, timeout, message):
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value is not None and value is not False:
            return value
        if process.poll() is not None:
            pytest.fail(f"CST exited early with code {process.returncode}: {message}")
        if time.monotonic() >= deadline:
            pytest.fail(message)
        time.sleep(0.1)


def _read_timing(path):
    lines = path.read_text(encoding="ascii").splitlines()
    return tuple(float(value.replace(",", ".")) for value in lines[1:4])


def test_warm_worker_runs_two_ack_gated_tasks_then_stops(cst_executable):
    session_id = new_session_id()
    tasks = (
        Task.create(session_id, {"R": "229", "L": "R + 30"}, expression_names=frozenset({"L"})),
        Task.create(session_id, {"R": "230", "L": "R + 29"}, expression_names=frozenset({"L"})),
    )
    source = Path(__file__).parent / "data" / "Pillbox" / "Pillbox.cst"
    root = Path.cwd() / ".pytest_cache" / "cst-p4" / session_id[:8]
    workspace = prepare_warm_worker_workspace(
        root, tasks, source, result_name="Frequency (Multiple Modes)/Mode 1"
    )
    log_path = root / "cst-warm-worker-v1.log"
    baseline = cst_processes(windows_process_snapshot())

    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(cst_executable), "-m", str(workspace.macro_path)],
            stdout=log, stderr=subprocess.STDOUT,
        )
        forced_cleanup = {}
        try:
            first = wait_completion_or_controller_exit(workspace, tasks[0], process, timeout=300)
            assert first.status is CompletionStatus.SUCCESS, first
            first_value = VBPostProcessor.cst0dreadout(workspace.tasks[0].result_path)
            time.sleep(1)
            assert workspace.protocol.read_completion(tasks[1]) is None
            workspace.protocol.acknowledge(first)

            second = wait_completion_or_controller_exit(workspace, tasks[1], process, timeout=300)
            assert second.status is CompletionStatus.SUCCESS, second
            second_value = VBPostProcessor.cst0dreadout(workspace.tasks[1].result_path)
            assert all(math.isfinite(value) and value > 0 for value in (first_value, second_value))
            assert first_value != second_value
            assert workspace.tasks[0].result_path.exists()
            workspace.protocol.acknowledge(second)

            workspace.protocol.request_stop(session_id)
            _wait_until(
                lambda: workspace.protocol.read_stop_ack(session_id), process, 60,
                "timed out waiting for StopAck",
            )
            wait_for_standard_exit(process, baseline, timeout=60)
        finally:
            forced_cleanup = force_cleanup(process, baseline)

    assert workspace.marker_path.read_text(encoding="ascii").strip() == "success"
    assert not forced_cleanup, f"standard CST shutdown required forced cleanup: {forced_cleanup}; inspect {log_path}"
    timings = tuple(_read_timing(artifact.timing_path) for artifact in workspace.tasks)
    assert all(value >= 0 for timing in timings for value in timing)
