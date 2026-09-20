import hashlib
import math
from pathlib import Path

import pytest

from csttool.managed_cstworker import ManagedCSTWorker
from test.cst_integration_support import (
    cst_processes,
    force_cleanup,
    windows_process_snapshot,
)


pytestmark = pytest.mark.integration


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_managed_pillbox_solves_and_reads_five_modes(cst_executable, tmp_path):
    source = Path(__file__).parent / "data" / "Pillbox" / "Pillbox.cst"
    source_hash = _sha256(source)
    root = tmp_path / "pillbox-five-modes"
    baseline = cst_processes(windows_process_snapshot())
    worker = None
    forced_cleanup = {}
    try:
        worker = ManagedCSTWorker(
            "five-modes",
            {
                "taskFileDir": str(root / "worker"),
                "resultDir": str(root / "results"),
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
                        "resultName": f"frequency_mode_{mode}",
                        "method": "Frequency",
                        "params": {"iModeNumber": mode},
                    }
                    for mode in range(1, 6)
                ],
            },
        )

        result = worker.runWithParam(
            "pillbox-five-modes",
            params={"nmodes": 5, "fmin": 400, "fmax": 1200},
        )

        assert result["TaskStatus"] == "Success", result
        values = [item["value"] for item in result["PostProcessResult"]]
        assert len(values) == 5
        assert all(math.isfinite(value) and value > 0 for value in values)
        assert values == sorted(values)
        assert len(set(values)) == 5
        assert worker.stop()
        assert worker.protocol.read_stop_ack(worker.session_id) is not None
        assert worker._process.returncode == 0
    finally:
        process = worker._process if worker is not None else None
        forced_cleanup = force_cleanup(process, baseline)

    assert _sha256(source) == source_hash
    assert not forced_cleanup, (
        "five-mode Pillbox Gate required forced cleanup: "
        f"{forced_cleanup}; inspect {worker.log_path if worker else root}"
    )
