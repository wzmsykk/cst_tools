from dataclasses import replace
import json
import subprocess
import time
from pathlib import Path

import pytest

from csttool.hom_project_profile import (
    HOM_PROFILE_V1,
    ResultTemplateRequirement,
)
from csttool.hom_native_results import read_hom_native_results
from csttool.protocol_hom_template_evaluation import read_result_template_inventory
from csttool.protocol_warm_worker import prepare_warm_worker_workspace
from csttool.protocol_worker import prepare_worker_workspace
from csttool.runtime_protocol import CompletionStatus, ErrorCode, Task, new_session_id
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
            native = read_hom_native_results(
                workspace.snapshot_path.with_suffix(""), HOM_PROFILE_V1
            )
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
        root, tasks, source, result_name=RESULT_NAME, profile=HOM_PROFILE_V1
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
                values.append(
                    read_hom_native_results(
                        artifact.snapshot_path.with_suffix(""), HOM_PROFILE_V1
                    )
                )
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
    inventory = read_result_template_inventory(workspace.profile_inventory_path)
    HOM_PROFILE_V1.validate_inventory(inventory)
    return {
        "profile_id": HOM_PROFILE_V1.profile_id,
        "profile_preflight_count": 1,
        "registered_template_count": len(inventory),
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
    source = Path(__file__).parent.parent / HOM_PROFILE_V1.source_project
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
    assert warm["profile_preflight_count"] == 1


def test_missing_hom_profile_template_stops_warm_session_before_first_solver(
    cst_executable,
):
    source = Path(__file__).parent.parent / HOM_PROFILE_V1.source_project
    missing = ResultTemplateRequirement(
        "P6.5 deliberately missing",
        "M0D",
        "3D Eigenmode Result",
        "2D and 3D Field Results",
    )
    profile = replace(
        HOM_PROFILE_V1,
        profile_id="hom-warm-missing-gate",
        required_templates=(*HOM_PROFILE_V1.required_templates, missing),
    )
    session_id = new_session_id()
    tasks = (
        Task.create(session_id, {"fmin": "720", "fmax": "800"}),
        Task.create(session_id, {"fmin": "800", "fmax": "880"}),
    )
    root = Path.cwd() / ".pytest_cache" / "cst-p6-5-missing" / session_id[:8]
    workspace = prepare_warm_worker_workspace(
        root, tasks, source, result_name=RESULT_NAME, profile=profile
    )
    baseline = cst_processes(windows_process_snapshot())
    with (root / "cst-p6-5-missing.log").open("wb") as log:
        process = subprocess.Popen(
            [str(cst_executable), "-m", str(workspace.macro_path)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        forced = {}
        try:
            completion = wait_completion_or_controller_exit(
                workspace, tasks[0], process, timeout=300
            )
            assert completion.status is CompletionStatus.FAILURE
            assert completion.error_code is ErrorCode.PROFILE_CAPABILITY_MISSING
            assert "P6.5 deliberately missing" in completion.error_message
            wait_for_standard_exit(process, baseline, timeout=120)
            assert all(not artifact.timing_path.exists() for artifact in workspace.tasks)
            assert workspace.protocol.read_completion(tasks[1]) is None
        finally:
            forced = force_cleanup(process, baseline)
    assert not forced, f"P6.5 fail-fast Gate required forced cleanup: {forced}"
