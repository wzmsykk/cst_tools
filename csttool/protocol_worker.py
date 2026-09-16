"""Build the independent one-shot CST Worker v1 used by the P3 gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from install_compat import resource_path

from .runtime_protocol import FileProtocol, Task


@dataclass(frozen=True, slots=True)
class WorkerWorkspace:
    root: Path
    protocol: FileProtocol
    task: Task
    project_path: Path
    snapshot_path: Path
    result_path: Path
    macro_path: Path
    marker_path: Path


def prepare_worker_workspace(
    root: str | Path,
    task: Task,
    source_project: str | Path,
    *,
    result_name: str,
) -> WorkerWorkspace:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    protocol = FileProtocol(root / "protocol")
    task_path = protocol.submit(task)
    completion_path = protocol.completed / f"{task.task_id}.completion"
    ack_path = protocol.acks / f"{task.task_id}.ack"
    project_path = root / "worker-input.cst"
    snapshot_path = root / "worker-result.cst"
    result_path = root / "worker-result" / "Result" / f"{result_name}.rd0"
    marker_path = root / "worker.result"
    macro_path = root / "runtime_worker_v1.bas"
    shutil.copy2(source_project, project_path)
    build_worker_macro(
        macro_path, task_path=task_path, completion_path=completion_path,
        ack_path=ack_path, snapshot_path=snapshot_path, result_path=result_path,
        project_path=project_path, marker_path=marker_path, session_id=task.session_id,
    )
    return WorkerWorkspace(root, protocol, task, project_path, snapshot_path,
                           result_path, macro_path, marker_path)


def build_worker_macro(
    destination: str | Path,
    *,
    task_path: str | Path,
    completion_path: str | Path,
    ack_path: str | Path,
    snapshot_path: str | Path,
    result_path: str | Path,
    project_path: str | Path,
    marker_path: str | Path,
    session_id: str,
) -> Path:
    codec = Path(resource_path("data/runtime_protocol_v1.vb")).read_text(encoding="utf-8")
    worker = Path(resource_path("data/runtime_worker_v1_main.vb")).read_text(encoding="utf-8")
    replacements = {
        "%TASK_PATH%": _vb_string(Path(task_path).absolute()),
        "%COMPLETION_PATH%": _vb_string(Path(completion_path).absolute()),
        "%ACK_PATH%": _vb_string(Path(ack_path).absolute()),
        "%SNAPSHOT_PATH%": _vb_string(Path(snapshot_path).absolute()),
        "%RESULT_PATH%": _vb_string(Path(result_path).absolute()),
        "%PROJECT_PATH%": _vb_string(Path(project_path).absolute()),
        "%MARKER_PATH%": _vb_string(Path(marker_path).absolute()),
        "%SESSION_ID%": _vb_string(session_id),
    }
    for placeholder, value in replacements.items():
        worker = worker.replace(placeholder, value)
    if "%" in worker:
        raise ValueError("worker macro contains an unresolved placeholder")
    output = "'#Language \"WWB-COM\"\n\nOption Explicit\n\n" + codec + "\n" + worker
    if output.lower().count("sub main") != 1:
        raise ValueError("worker macro must contain exactly one Sub Main")
    destination = Path(destination)
    destination.write_text(output, encoding="ascii", newline="\n")
    return destination


def _vb_string(value: object) -> str:
    text = str(value)
    if not text.isascii() or "\r" in text or "\n" in text:
        raise ValueError("protocol v1 worker paths and IDs must be ASCII")
    return text.replace('"', '""')
