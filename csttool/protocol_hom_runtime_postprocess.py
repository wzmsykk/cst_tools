"""Build the bounded P5.5 HOM runtime post-processing Gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from install_compat import resource_path

from .hom_result_plan import IntegrationLine
from .protocol_worker import WorkerWorkspace, _vb_string, prepare_worker_workspace
from .runtime_protocol import Task


_GATE_LINES = {
    "x_5mm": IntegrationLine("x", yoffset_mm=5),
    "y_5mm": IntegrationLine("y", xoffset_mm=5),
    "z_5mm": IntegrationLine("z", yoffset_mm=5),
    "z_7_5mm": IntegrationLine("z", yoffset_mm=7.5),
}


@dataclass(frozen=True, slots=True)
class HomRuntimePostprocessWorkspace:
    worker: WorkerWorkspace
    result_paths: Mapping[str, Path]
    integration_lines: Mapping[str, IntegrationLine]


def prepare_hom_runtime_postprocess_workspace(
    root: str | Path,
    task: Task,
    source_project: str | Path,
    *,
    result_name: str,
) -> HomRuntimePostprocessWorkspace:
    worker = prepare_worker_workspace(
        root, task, source_project, result_name=result_name
    )
    output_dir = worker.root / "runtime-results"
    output_dir.mkdir()
    result_paths = {
        key: output_dir / f"r-over-q-{key.replace('_', '-')}.txt"
        for key in _GATE_LINES
    }
    _install_fixed_runtime_extension(
        worker.macro_path, output_dir, result_paths, _GATE_LINES
    )
    return HomRuntimePostprocessWorkspace(
        worker,
        MappingProxyType(result_paths),
        MappingProxyType(dict(_GATE_LINES)),
    )


def _install_fixed_runtime_extension(
    macro_path: Path,
    output_dir: Path,
    result_paths: Mapping[str, Path],
    integration_lines: Mapping[str, IntegrationLine],
) -> None:
    macro = macro_path.read_text(encoding="ascii")
    extension = Path(
        resource_path("data/postprocess/EigenResult_Complex_All.vb")
    ).read_text(encoding="ascii")
    marker = "' Independent one-shot Worker v1. This does not replace legacy worker.vb."
    if marker not in macro:
        raise ValueError("one-shot worker marker is missing")
    macro = macro.replace(marker, extension + "\n\n" + marker, 1)

    flush = '    stage = "flush"\n'
    if macro.count(flush) != 1:
        raise ValueError("one-shot worker flush stage is ambiguous")
    directory = _vb_string(str(output_dir.absolute()) + "\\")
    calls = []
    for key, line in integration_lines.items():
        filename = _vb_string(result_paths[key].name)
        calls.append(
            '    EigenResult_Complex_output 1, "R over Q", '
            f'{line.axis_number}, {line.xoffset_mm:g}, {line.yoffset_mm:g}, '
            f'{line.zoffset_mm:g}, "{directory}", "{filename}"\n'
        )
    postprocess = (
        '    stage = "runtime-postprocess"\n'
        '    CSTPW_WriteMarker "%MARKER_PATH%", "stage:runtime-postprocess"\n'
        + "".join(calls)
        + "\n"
        + flush
    )
    marker_path = _vb_string(worker_marker_path(macro))
    postprocess = postprocess.replace("%MARKER_PATH%", marker_path)
    macro = macro.replace(flush, postprocess, 1)
    if macro.lower().count("sub main") != 1:
        raise ValueError("P5.5 worker must contain exactly one Sub Main")
    macro_path.write_text(macro, encoding="ascii", newline="\n")


def worker_marker_path(macro: str) -> str:
    prefix = 'CSTPW_WriteMarker "'
    start = macro.find(prefix)
    if start < 0:
        raise ValueError("worker marker path is missing")
    start += len(prefix)
    end = macro.find('",', start)
    if end < 0:
        raise ValueError("worker marker path is malformed")
    return macro[start:end]
