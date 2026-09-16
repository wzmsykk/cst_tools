"""Build the bounded P5.5 HOM runtime post-processing Gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from install_compat import resource_path

from .protocol_worker import WorkerWorkspace, _vb_string, prepare_worker_workspace
from .runtime_protocol import Task


@dataclass(frozen=True, slots=True)
class HomRuntimePostprocessWorkspace:
    worker: WorkerWorkspace
    r_over_q_5mm_path: Path
    r_over_q_7_5mm_path: Path


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
    path_5mm = output_dir / "r-over-q-5mm.txt"
    path_7_5mm = output_dir / "r-over-q-7_5mm.txt"
    _install_fixed_runtime_extension(worker.macro_path, output_dir)
    return HomRuntimePostprocessWorkspace(worker, path_5mm, path_7_5mm)


def _install_fixed_runtime_extension(macro_path: Path, output_dir: Path) -> None:
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
    postprocess = (
        '    stage = "runtime-postprocess"\n'
        '    CSTPW_WriteMarker "%MARKER_PATH%", "stage:runtime-postprocess"\n'
        f'    EigenResult_Complex_output 1, "R over Q", 3, 0, 5, 0, "{directory}", "r-over-q-5mm.txt"\n'
        f'    EigenResult_Complex_output 1, "R over Q", 3, 0, 7.5, 0, "{directory}", "r-over-q-7_5mm.txt"\n\n'
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
