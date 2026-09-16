"""Build the opt-in CST/WWB contract test macro for protocol v1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from install_compat import resource_path

from .runtime_protocol import FileProtocol, Task


@dataclass(frozen=True, slots=True)
class ContractWorkspace:
    root: Path
    protocol: FileProtocol
    task: Task
    macro_path: Path
    completion_path: Path
    ack_path: Path
    marker_path: Path


def prepare_contract_workspace(root: str | Path, task: Task) -> ContractWorkspace:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    protocol = FileProtocol(root / "protocol")
    task_path = protocol.submit(task)
    completion_path = protocol.completed / f"{task.task_id}.completion"
    ack_path = protocol.acks / f"{task.task_id}.ack"
    marker_path = root / "contract.result"
    macro_path = root / "runtime_protocol_contract.bas"
    build_contract_macro(
        macro_path,
        task_path=task_path,
        completion_path=completion_path,
        ack_path=ack_path,
        marker_path=marker_path,
        session_id=task.session_id,
    )
    return ContractWorkspace(
        root=root,
        protocol=protocol,
        task=task,
        macro_path=macro_path,
        completion_path=completion_path,
        ack_path=ack_path,
        marker_path=marker_path,
    )


def build_contract_macro(
    destination: str | Path,
    *,
    task_path: str | Path,
    completion_path: str | Path,
    ack_path: str | Path,
    marker_path: str | Path,
    session_id: str,
) -> Path:
    codec_path = Path(resource_path("data/runtime_protocol_v1.vb"))
    harness_path = Path(resource_path("data/runtime_protocol_contract_main.vb"))
    codec = codec_path.read_text(encoding="utf-8")
    harness = harness_path.read_text(encoding="utf-8")
    replacements = {
        "%TASK_PATH%": _vb_string(Path(task_path).absolute()),
        "%COMPLETION_PATH%": _vb_string(Path(completion_path).absolute()),
        "%ACK_PATH%": _vb_string(Path(ack_path).absolute()),
        "%MARKER_PATH%": _vb_string(Path(marker_path).absolute()),
        "%SESSION_ID%": _vb_string(session_id),
    }
    for placeholder, value in replacements.items():
        harness = harness.replace(placeholder, value)
    if "%" in harness:
        raise ValueError("contract macro contains an unresolved placeholder")

    output = "'#Language \"WWB-COM\"\n\nOption Explicit\n\n" + codec + "\n" + harness
    if output.lower().count("sub main") != 1:
        raise ValueError("contract macro must contain exactly one Sub Main")
    destination = Path(destination)
    destination.write_text(output, encoding="ascii", newline="\n")
    return destination


def _vb_string(value: object) -> str:
    text = str(value)
    if not text.isascii() or "\r" in text or "\n" in text:
        raise ValueError("protocol v1 contract paths and IDs must be ASCII")
    return text.replace('"', '""')
