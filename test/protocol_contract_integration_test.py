import json
import re
import subprocess
import time
from pathlib import Path

import pytest

from csttool.protocol_contract import prepare_contract_workspace
from csttool.runtime_protocol import (
    CompletionStatus,
    ParameterAssignment,
    ParameterKind,
    Task,
    new_session_id,
)


pytestmark = pytest.mark.integration


def _windows_process_snapshot():
    command = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = completed.stdout.strip()
    if not payload:
        return {}
    records = json.loads(payload)
    if isinstance(records, dict):
        records = [records]
    return {
        int(record["ProcessId"]): (
            int(record["ParentProcessId"]),
            record["Name"],
        )
        for record in records
    }


def _cst_processes(snapshot):
    return {
        pid: name
        for pid, (_, name) in snapshot.items()
        if name.lower().startswith("cst")
    }


def _new_cst_processes(baseline):
    current = _cst_processes(_windows_process_snapshot())
    return {pid: name for pid, name in current.items() if pid not in baseline}


def _force_cleanup(process, baseline):
    forced = _new_cst_processes(baseline)
    for pid in forced:
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)
    return forced


def _wait_for_standard_exit(process, baseline, timeout=30):
    process.wait(timeout=timeout)
    if process.returncode != 0:
        raise AssertionError(f"CST OLE controller exited with code {process.returncode}")

    deadline = time.monotonic() + 10
    while True:
        remaining = _new_cst_processes(baseline)
        if not remaining:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"standard Project.Quit left CST processes running: {remaining}"
            )
        time.sleep(0.1)


def _wait_completion_or_controller_exit(workspace, task, process, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        completion = workspace.protocol.read_completion(task)
        if completion is not None:
            return completion
        if process.poll() is not None:
            raise AssertionError(
                "CST OLE controller exited before writing Completion; "
                f"return code={process.returncode}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for task {task.task_id}")
        time.sleep(0.1)


def _versioned_progid(cst_executable):
    match = re.search(r"CST Studio Suite (\d{4})", str(cst_executable), re.IGNORECASE)
    if match is None:
        raise AssertionError(
            "cannot derive a versioned CST OLE ProgID from --cst-exe; "
            "expected a path containing 'CST Studio Suite YYYY'"
        )
    return f"CSTStudio.Application.{match.group(1)}"


def test_cst_wwb_executes_protocol_golden_contract(cst_executable, tmp_path):
    session_id = new_session_id()
    task = Task.create(
        session_id,
        {"Rx": "90.0", "L": "2 * Rx = L"},
        expression_names=frozenset({"L"}),
    )
    workspace = prepare_contract_workspace(tmp_path, task)
    log_path = tmp_path / "cst-contract.log"
    baseline = _cst_processes(_windows_process_snapshot())
    controller = Path(__file__).parent / "support" / "run_cst_contract.ps1"

    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(controller),
                "-ProgId",
                _versioned_progid(cst_executable),
                "-MacroPath",
                str(workspace.macro_path),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        forced_cleanup = {}
        try:
            completion = _wait_completion_or_controller_exit(
                workspace, task, process, timeout=60
            )
            assert completion.status is CompletionStatus.SUCCESS
            workspace.protocol.acknowledge(completion)
            deadline = time.monotonic() + 30
            while not workspace.marker_path.exists():
                if process.poll() is not None:
                    pytest.fail(f"CST exited before writing the contract marker: {process.returncode}")
                if time.monotonic() >= deadline:
                    pytest.fail("timed out waiting for the contract marker")
                time.sleep(0.1)
            _wait_for_standard_exit(process, baseline)
        finally:
            forced_cleanup = _force_cleanup(process, baseline)

    assert workspace.marker_path.read_text(encoding="ascii").strip() == "success"
    assert not forced_cleanup, (
        "standard CST shutdown failed; forced cleanup was required for "
        f"{forced_cleanup}. Inspect {log_path}"
    )
