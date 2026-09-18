from pathlib import Path

import pytest

from csttool.managed_cstworker import ManagedCSTWorker
from test.cst_integration_support import (
    cst_processes,
    force_cleanup,
    windows_process_snapshot,
)


pytestmark = pytest.mark.integration


def test_managed_worker_runs_repeated_tasks_and_standardly_exits(
    cst_executable, tmp_path
):
    source = Path(__file__).parent / "data" / "Pillbox" / "Pillbox.cst"
    root = tmp_path / "managed-worker"
    baseline = cst_processes(windows_process_snapshot())
    worker = None
    forced_cleanup = {}
    try:
        worker = ManagedCSTWorker(
            "gate",
            {
                "taskFileDir": str(root / "worker"),
                "resultDir": str(root / "results"),
                "cstPath": str(source),
                "CSTENVPATH": str(cst_executable),
                "paramList": [
                    {"name": "R", "type": "double"},
                    {"name": "L", "type": "expression"},
                ],
                "postProcess": [
                    {
                        "resultName": "frequency",
                        "method": "Frequency",
                        "params": {"iModeNumber": 1},
                    }
                ],
            },
        )

        first = worker.runWithParam(
            "first", params={"R": "229", "L": "R + 30"}
        )
        second = worker.runWithParam(
            "second", params={"R": "230", "L": "R + 29"}
        )

        assert first["TaskStatus"] == "Success", first
        assert second["TaskStatus"] == "Success", second
        first_frequency = first["PostProcessResult"][0]["value"]
        second_frequency = second["PostProcessResult"][0]["value"]
        assert first_frequency > 0
        assert second_frequency > 0
        assert first_frequency != second_frequency
        assert worker.stop()
        assert worker.protocol.read_stop_ack(worker.session_id) is not None
        assert worker._process.returncode == 0
    finally:
        process = worker._process if worker is not None else None
        forced_cleanup = force_cleanup(process, baseline)

    assert not forced_cleanup, (
        "managed Worker required forced cleanup: "
        f"{forced_cleanup}; inspect {worker.log_path if worker else root}"
    )
