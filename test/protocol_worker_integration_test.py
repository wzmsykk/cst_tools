import math
import subprocess
import time
from pathlib import Path

import pytest

from csttool.postprocess_cst import VBPostProcessor
from csttool.protocol_worker import prepare_worker_workspace
from csttool.runtime_protocol import CompletionStatus, Task, new_session_id
from test.cst_integration_support import (
    cst_processes, force_cleanup,
    wait_completion_or_controller_exit, wait_for_standard_exit,
    windows_process_snapshot,
)


pytestmark = pytest.mark.integration


def test_worker_v1_solves_reads_native_rd0_then_acknowledges(cst_executable):
    task = Task.create(
        new_session_id(), {"nmodes": "1", "L": "R + 30"},
        expression_names=frozenset({"L"}),
    )
    source_project = Path(__file__).parent / "data" / "Pillbox" / "Pillbox.cst"
    workspace_root = Path.cwd() / ".pytest_cache" / "cst-p3" / task.task_id[:8]
    workspace = prepare_worker_workspace(
        workspace_root, task, source_project,
        result_name="Frequency (Multiple Modes)/Mode 1",
    )
    log_path = workspace.root / "cst-worker-v1.log"
    baseline = cst_processes(windows_process_snapshot())
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(cst_executable), "-m", str(workspace.macro_path)],
            stdout=log, stderr=subprocess.STDOUT,
        )
        forced_cleanup = {}
        try:
            completion = wait_completion_or_controller_exit(workspace, task, process, timeout=300)
            assert completion.status is CompletionStatus.SUCCESS, completion
            frequency = VBPostProcessor.cst0dreadout(workspace.result_path)
            assert frequency is not None and math.isfinite(frequency) and frequency > 0
            workspace.protocol.acknowledge(completion)
            deadline = time.monotonic() + 60
            while not workspace.marker_path.exists():
                if process.poll() is not None:
                    pytest.fail(f"CST exited before writing worker marker: {process.returncode}")
                if time.monotonic() >= deadline:
                    pytest.fail("timed out waiting for worker marker")
                time.sleep(0.1)
            wait_for_standard_exit(process, baseline, timeout=60)
        finally:
            forced_cleanup = force_cleanup(process, baseline)

    assert workspace.marker_path.read_text(encoding="ascii").strip() == "success"
    assert not forced_cleanup, (
        "standard CST shutdown failed; forced cleanup was required for "
        f"{forced_cleanup}. Inspect {log_path}"
    )
