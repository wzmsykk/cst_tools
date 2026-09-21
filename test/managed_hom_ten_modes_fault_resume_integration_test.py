import json
import math
import os
from pathlib import Path
import time

import pytest

from csttool.hom_project_profile import HOM_PROFILE_V1
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

PPS = [
    {"resultName": "frequency", "method": "Frequency", "params": {"iModeNumber": 1}},
    {"resultName": "R_divide_Q", "method": "R_over_Q", "params": {"iModeNumber": 1, "xoffset": 0.0, "yoffset": 0.0}},
    {"resultName": "R_divide_Q_5mm", "method": "R_over_Q", "params": {"iModeNumber": 1, "xoffset": 0.0, "yoffset": 5.0}},
    {"resultName": "R_divide_Q_10mm", "method": "R_over_Q", "params": {"iModeNumber": 1, "xoffset": 0.0, "yoffset": 10.0}},
    {"resultName": "Shunt_Impedance", "method": "Shunt_Impedance", "params": {"iModeNumber": 1, "xoffset": 0.0, "yoffset": 0.0}},
    {"resultName": "Total_Loss", "method": "Total_Loss", "params": {"iModeNumber": 1}},
    {"resultName": "Q-factor", "method": "Q_Factor", "params": {"iModeNumber": 1}},
]


def _config(
    project: Path,
    worker_id: str,
    cst_executable: Path,
    source: Path | None = None,
) -> dict:
    source = source or (Path(__file__).parent.parent / HOM_PROFILE_V1.source_project)
    return {
        "taskFileDir": str(project / "temp" / f"worker_{worker_id}"),
        "resultDir": str(project / "result" / f"worker_{worker_id}"),
        "cstPath": str(source),
        "CSTENVPATH": str(cst_executable),
        "runInBackground": True,
        "paramList": [
            {"name": "fmin", "type": "double"},
            {"name": "fmax", "type": "double"},
        ],
        "postProcess": PPS,
    }


def _atomic_checkpoint(path: Path, modes: list[dict], events: list[dict]) -> None:
    document = {"schema_version": 1, "modes": modes, "events": events}
    temporary = path.with_suffix(".json.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _result_values(result: dict) -> dict[str, float]:
    assert result["TaskStatus"] == "Success", result
    values = {item["resultName"]: float(item["value"]) for item in result["PostProcessResult"]}
    assert set(values) == {item["resultName"] for item in PPS}
    assert all(math.isfinite(value) for value in values.values())
    return values


def _run_next(worker: ManagedCSTWorker, lo: float) -> dict:
    result = worker.runWithParam(
        f"hom_from_{lo:.6f}", params={"fmin": lo, "fmax": lo + 50.0}
    )
    return _result_values(result)


def _dispatch_next_without_controller(worker, lo: float) -> tuple[Task, int]:
    log_offset = worker.log_path.stat().st_size
    task = Task.create(worker.session_id, {"fmin": lo, "fmax": lo + 50.0})
    worker.marker_path.write_text(f"dispatched:{task.task_id}", encoding="ascii")
    atomic_publish(worker.task_path, encode_task(task))
    return task, log_offset


def _wait_solver(worker, log_offset: int, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if worker._process.poll() is not None:
            pytest.fail(f"CST exited before injected fault: {worker._process.returncode}")
        with worker.log_path.open("rb") as stream:
            stream.seek(log_offset)
            new_log = stream.read().decode("utf-8", errors="replace")
        if "Eigenmode" in new_log:
            return
        time.sleep(0.1)
    pytest.fail("HOM solver did not start before fault injection")


def _read_recovered_task(worker, task: Task) -> dict[str, float]:
    worker.postprocess.setResultDir(worker.result_root / task.task_id)
    worker.postprocess.setCSTRunResultDir(worker.result_root / task.task_id / "project")
    return {
        item["resultName"]: float(item["value"])
        for item in worker.postprocess.readAllResults()
    }


def _latest_snapshot(worker: ManagedCSTWorker) -> Path:
    snapshots = sorted(
        worker.result_root.glob("*/project.cst"),
        key=lambda path: path.stat().st_mtime_ns,
    )
    assert snapshots, "completed HOM task did not create a project snapshot"
    return snapshots[-1]


def test_hom_runs_ten_ordered_modes_across_three_fault_recovery_paths(
    cst_executable, tmp_path
):
    project = tmp_path / "hom-ten-mode-recovery"
    checkpoint = project / "hom_ten_modes_checkpoint.json"
    baseline = cst_processes(windows_process_snapshot())
    workers = []
    modes = []
    events = []
    next_lo = 500.0
    forced = {}

    def accept(values):
        nonlocal next_lo
        frequency = values["frequency"]
        assert not modes or frequency > modes[-1]["frequency"]
        modes.append({"index": len(modes) + 1, **values})
        next_lo = frequency + 1e-6
        _atomic_checkpoint(checkpoint, modes, events)
        print(f"accepted HOM mode {len(modes)}: {frequency:.9f} MHz", flush=True)

    def solve_and_accept(worker):
        nonlocal next_lo
        for _ in range(20):
            lo = next_lo
            values = _run_next(worker, lo)
            if values["frequency"] > 0:
                accept(values)
                return
            events.append({"reason": "empty-window", "lo": lo, "hi": lo + 50.0})
            next_lo = lo + 50.0
            _atomic_checkpoint(checkpoint, modes, events)
            print(f"empty HOM window: {lo:.6f}-{lo + 50.0:.6f} MHz", flush=True)
        pytest.fail("too many consecutive empty HOM windows")

    try:
        seed_root_value = os.environ.get("HOM_TEN_MODE_RECOVERY_SEED")
        resumed_from_seed = bool(seed_root_value)
        if seed_root_value:
            seed_root = Path(seed_root_value)
            seed_document = json.loads(
                (seed_root / "hom_ten_modes_checkpoint.json").read_text(
                    encoding="utf-8"
                )
            )
            modes.extend(seed_document["modes"])
            events.extend(seed_document["events"])
            assert len(modes) == 6
            next_lo = modes[-1]["frequency"] + 1e-6
            seed_snapshots = sorted(
                (seed_root / "result" / "worker_1").rglob("project.cst"),
                key=lambda path: path.stat().st_mtime_ns,
            )
            assert seed_snapshots
            first_snapshot = seed_snapshots[-1]
            _atomic_checkpoint(checkpoint, modes, events)
            print("resumed test harness from six-mode atomic checkpoint", flush=True)
        else:
            first = ManagedCSTWorker("0", _config(project, "0", cst_executable))
            workers.append(first)
            for _ in range(3):
                solve_and_accept(first)
            events.append({"after_mode": 3, "reason": "user-safe-pause"})
            _atomic_checkpoint(checkpoint, modes, events)
            assert first.stop()
            first_snapshot = _latest_snapshot(first)

        second = ManagedCSTWorker(
            "1", _config(project, "1", cst_executable, first_snapshot)
        )
        workers.append(second)
        for _ in range(0 if resumed_from_seed else 3):
            solve_and_accept(second)
        task7, task7_log_offset = _dispatch_next_without_controller(second, next_lo)
        _wait_solver(second, task7_log_offset)
        recovered = recover_project_sessions(project, timeout_per_session=600)
        assert second.session_id in {item.session_id for item in recovered}
        receipt = json.loads((second.root / "recovery.json").read_text(encoding="utf-8"))
        assert receipt["disposition"] == "standard-stop"
        assert receipt["completion_task_id"] == task7.task_id
        recovered_values = _read_recovered_task(second, task7)
        assert recovered_values["frequency"] > 0
        accept(recovered_values)
        events.append({"after_mode": 7, "reason": "controller-loss", "recovery": "standard-stop"})
        _atomic_checkpoint(checkpoint, modes, events)
        second._close_log()
        second_snapshot = second.result_root / task7.task_id / "project.cst"
        assert second_snapshot.is_file()

        third = ManagedCSTWorker(
            "2", _config(project, "2", cst_executable, second_snapshot)
        )
        workers.append(third)
        solve_and_accept(third)
        mode8_snapshot = _latest_snapshot(third)
        task9_abandoned, task9_log_offset = _dispatch_next_without_controller(
            third, next_lo
        )
        _wait_solver(third, task9_log_offset)
        third.emergency_terminate()
        recovered = recover_project_sessions(project, timeout_per_session=60)
        assert third.session_id in {item.session_id for item in recovered}
        receipt = json.loads((third.root / "recovery.json").read_text(encoding="utf-8"))
        assert receipt["disposition"] == "abandoned-dead"
        assert receipt["completion_task_id"] in {None, task9_abandoned.task_id}
        assert len(modes) == 8
        events.append({"after_mode": 8, "reason": "cst-process-death", "recovery": "abandoned-dead"})
        _atomic_checkpoint(checkpoint, modes, events)

        fourth = ManagedCSTWorker(
            "3", _config(project, "3", cst_executable, mode8_snapshot)
        )
        workers.append(fourth)
        while len(modes) < 10:
            solve_and_accept(fourth)
        assert fourth.stop()

        frequencies = [item["frequency"] for item in modes]
        assert len(modes) == 10
        assert frequencies == sorted(frequencies)
        assert len(set(frequencies)) == 10
        assert all(len({key for key in item if key not in {"index"}}) == 7 for item in modes)
        assert not [item for item in discover_managed_sessions(project) if item.needs_recovery]
        final = json.loads(checkpoint.read_text(encoding="utf-8"))
        assert len(final["modes"]) == 10
        recovery_reasons = [
            event["reason"]
            for event in final["events"]
            if event["reason"] != "empty-window"
        ]
        assert recovery_reasons == [
            "user-safe-pause", "controller-loss", "cst-process-death"
        ]
    finally:
        for worker in workers:
            process = worker._process
            if process is not None and process.poll() is None:
                try:
                    worker.stop()
                except Exception:
                    worker.emergency_terminate()
            forced.update(force_cleanup(process, baseline))

    assert not forced, f"HOM ten-mode recovery Gate leaked CST: {forced}"
