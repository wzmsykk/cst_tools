import json
from pathlib import Path
from threading import Thread
import time

import pytest

from csttool.managed_cstworker import ManagedCSTWorker
from test.cst_integration_support import (
    cst_processes,
    force_cleanup,
    windows_process_snapshot,
)


pytestmark = pytest.mark.integration


def _config(root, cst_executable, progress_callback=None):
    source_root = Path(__file__).parent / "data" / "Pillbox"
    return {
        "taskFileDir": str(root / "runtime"),
        "resultDir": str(root / "results"),
        "cstPath": str(source_root / "Pillbox.cst"),
        "CSTENVPATH": str(cst_executable),
        "paramList": json.loads(
            (source_root / "params.json").read_text(encoding="utf-8")
        ),
        "postProcess": [
            {
                "resultName": "frequency",
                "method": "Frequency",
                "params": {"iModeNumber": 1},
            }
        ],
        "runInBackground": True,
        "progressCallback": progress_callback,
    }


def _run_one_then_stop(worker, lo, hi):
    result_box = []
    failure_box = []

    def run():
        try:
            result_box.append(
                worker.runWithParam(
                    f"pillbox_{lo:g}_{hi:g}",
                    params={"nmodes": 1, "fmin": lo, "fmax": hi},
                )
            )
        except Exception as exc:
            failure_box.append(exc)

    run_thread = Thread(target=run)
    run_thread.start()
    deadline = time.monotonic() + 30
    while not worker.marker_path.read_text(encoding="ascii").startswith("dispatched:"):
        if time.monotonic() >= deadline:
            pytest.fail("managed Pillbox task was not dispatched")
        time.sleep(0.1)

    stop_thread = Thread(target=worker.stop)
    stop_thread.start()
    run_thread.join(300)
    stop_thread.join(120)

    assert not run_thread.is_alive()
    assert not stop_thread.is_alive()
    assert not failure_box
    assert result_box[0]["TaskStatus"] == "Success"
    assert result_box[0]["PostProcessResult"]
    assert worker.marker_path.read_text(encoding="ascii").strip() == "stopped"
    assert worker._process.poll() == 0
    return result_box[0]


def test_pillbox_managed_worker_stops_safely_then_resumes_in_new_session(
    cst_executable, tmp_path
):
    baseline = cst_processes(windows_process_snapshot())
    workers = []
    forced = {}
    progress = []
    try:
        first = ManagedCSTWorker(
            "stop", _config(tmp_path / "first", cst_executable, progress.append)
        )
        workers.append(first)
        first_result = _run_one_then_stop(first, 500, 550)

        resumed = ManagedCSTWorker(
            "resume",
            _config(tmp_path / "resumed", cst_executable, progress.append),
        )
        workers.append(resumed)
        resumed_result = _run_one_then_stop(resumed, 550, 600)

        assert first_result["RunName"] == "pillbox_500_550"
        assert resumed_result["RunName"] == "pillbox_550_600"
        assert any(item.local_percent is not None for item in progress)
        assert any(
            item.interval_lo == 500 and item.interval_hi == 550
            for item in progress
        )
    finally:
        for worker in workers:
            process = worker._process
            if process is not None and process.poll() is None:
                try:
                    worker.stop()
                except Exception:
                    pass
                if process.poll() is None:
                    forced.update(force_cleanup(process, baseline))

    assert not forced, f"Pillbox Gate required forced cleanup: {forced}"
