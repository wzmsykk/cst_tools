import json
import subprocess
import time
from pathlib import Path

import pytest

from csttool.hom_native_results import read_hom_native_results
from csttool.protocol_warm_worker import prepare_warm_worker_workspace
from csttool.protocol_worker import prepare_worker_workspace
from csttool.runtime_protocol import CompletionStatus, Task, new_session_id
from test.cst_integration_support import (
    cst_processes, force_cleanup, wait_completion_or_controller_exit,
    wait_for_standard_exit, windows_process_snapshot,
)


pytestmark = pytest.mark.integration
RESULT_NAME = "Frequency (Multiple Modes)/Mode 1"


def _timing(path):
    lines = path.read_text(encoding="ascii").splitlines()
    return {
        "rebuild_seconds": float(lines[1].replace(",", ".")),
        "solve_seconds": float(lines[2].replace(",", ".")),
        "flush_seconds": float(lines[3].replace(",", ".")),
    }


def _run_cold(cst_executable, root, source, parameters):
    session_id = new_session_id()
    task = Task.create(session_id, parameters)
    workspace = prepare_worker_workspace(root, task, source, result_name=RESULT_NAME)
    baseline = cst_processes(windows_process_snapshot())
    started = time.monotonic()
    with (root / "cst-cold.log").open("wb") as log:
        process = subprocess.Popen(
            [str(cst_executable), "-m", str(workspace.macro_path)],
            stdout=log, stderr=subprocess.STDOUT,
        )
        forced = {}
        try:
            completion = wait_completion_or_controller_exit(workspace, task, process, timeout=1800)
            assert completion.status is CompletionStatus.SUCCESS, completion
            native = read_hom_native_results(workspace.snapshot_path.with_suffix(""))
            workspace.protocol.acknowledge(completion)
            wait_for_standard_exit(process, baseline, timeout=120)
        finally:
            forced = force_cleanup(process, baseline)
    assert not forced, f"Cold worker required forced cleanup: {forced}"
    return {
        "native_results": {key: result.value for key, result in native.items()},
        "wall_seconds": time.monotonic() - started,
        **_timing(workspace.timing_path),
    }


def _run_warm(cst_executable, root, source, parameter_sets):
    session_id = new_session_id()
    tasks = tuple(Task.create(session_id, parameters) for parameters in parameter_sets)
    workspace = prepare_warm_worker_workspace(
        root, tasks, source, result_name=RESULT_NAME
    )
    baseline = cst_processes(windows_process_snapshot())
    values = []
    started = time.monotonic()
    with (root / "cst-warm.log").open("wb") as log:
        process = subprocess.Popen(
            [str(cst_executable), "-m", str(workspace.macro_path)],
            stdout=log, stderr=subprocess.STDOUT,
        )
        forced = {}
        try:
            for task, artifact in zip(tasks, workspace.tasks):
                completion = wait_completion_or_controller_exit(
                    workspace, task, process, timeout=1800
                )
                assert completion.status is CompletionStatus.SUCCESS, completion
                values.append(read_hom_native_results(artifact.snapshot_path.with_suffix("")))
                workspace.protocol.acknowledge(completion)
            workspace.protocol.request_stop(session_id)
            deadline = time.monotonic() + 60
            while workspace.protocol.read_stop_ack(session_id) is None:
                if process.poll() is not None:
                    pytest.fail("Warm HOM worker exited before StopAck")
                if time.monotonic() >= deadline:
                    pytest.fail("timed out waiting for Warm HOM StopAck")
                time.sleep(0.1)
            wait_for_standard_exit(process, baseline, timeout=120)
        finally:
            forced = force_cleanup(process, baseline)
    assert not forced, f"Warm worker required forced cleanup: {forced}"
    return {
        "wall_seconds": time.monotonic() - started,
        "tasks": [
            {
                "native_results": {key: result.value for key, result in value.items()},
                **_timing(artifact.timing_path),
            }
            for value, artifact in zip(values, workspace.tasks)
        ],
    }


def test_fixed_hom_structure_warm_frequency_scan_is_faster_and_consistent(cst_executable):
    source = Path(__file__).parent.parent / "project" / "HOM analysis" / "HOM analysis_clean.cst"
    parameter_sets = (
        {"fmin": "720", "fmax": "800"},
        {"fmin": "800", "fmax": "880"},
    )
    root = Path.cwd() / ".pytest_cache" / "cst-p4-5" / new_session_id()[:8]
    root.mkdir(parents=True)

    cold = [
        _run_cold(cst_executable, root / f"cold-{index}", source, parameters)
        for index, parameters in enumerate(parameter_sets)
    ]
    warm = _run_warm(cst_executable, root / "warm", source, parameter_sets)
    report = {
        "project": str(source),
        "parameter_sets": parameter_sets,
        "cold": cold,
        "warm": warm,
        "cold_wall_total_seconds": sum(run["wall_seconds"] for run in cold),
        "warm_wall_total_seconds": warm["wall_seconds"],
    }
    report["wall_speedup"] = report["cold_wall_total_seconds"] / report["warm_wall_total_seconds"]
    (root / "benchmark.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8", newline="\n"
    )

    for cold_run, warm_run in zip(cold, warm["tasks"]):
        assert warm_run["native_results"] == pytest.approx(
            cold_run["native_results"], abs=1e-6
        )
    assert report["warm_wall_total_seconds"] < report["cold_wall_total_seconds"]
