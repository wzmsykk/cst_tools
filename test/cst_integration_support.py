"""Shared process/lifecycle helpers for opt-in real-CST gates."""

import json
import re
import subprocess
import time


def windows_process_snapshot():
    command = ("Get-CimInstance Win32_Process | Select-Object "
               "ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True, capture_output=True, text=True,
    )
    payload = completed.stdout.strip()
    if not payload:
        return {}
    records = json.loads(payload)
    if isinstance(records, dict):
        records = [records]
    return {int(r["ProcessId"]): (int(r["ParentProcessId"]), r["Name"])
            for r in records}


def cst_processes(snapshot):
    return {pid: name for pid, (_, name) in snapshot.items()
            if name.lower().startswith("cst")}


def new_cst_processes(baseline):
    current = cst_processes(windows_process_snapshot())
    return {pid: name for pid, name in current.items() if pid not in baseline}


def force_cleanup(process, baseline):
    forced = new_cst_processes(baseline)
    for pid in forced:
        subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                       check=False, capture_output=True)
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)
    return forced


def wait_for_standard_exit(process, baseline, timeout=30):
    process.wait(timeout=timeout)
    if process.returncode != 0:
        raise AssertionError(f"CST OLE controller exited with code {process.returncode}")
    deadline = time.monotonic() + 10
    while True:
        remaining = new_cst_processes(baseline)
        if not remaining:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(f"standard Project.Quit left CST processes running: {remaining}")
        time.sleep(0.1)


def wait_completion_or_controller_exit(workspace, task, process, timeout):
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


def versioned_progid(cst_executable):
    match = re.search(r"CST Studio Suite (\d{4})", str(cst_executable), re.IGNORECASE)
    if match is None:
        raise AssertionError(
            "cannot derive a versioned CST OLE ProgID from --cst-exe; "
            "expected a path containing 'CST Studio Suite YYYY'"
        )
    return f"CSTStudio.Application.{match.group(1)}"
