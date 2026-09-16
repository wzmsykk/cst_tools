import json
import math
import subprocess
from pathlib import Path

import pytest

from csttool.hom_native_results import read_hom_native_results
from csttool.postprocess_cst import VBPostProcessor
from csttool.protocol_hom_runtime_postprocess import (
    prepare_hom_runtime_postprocess_workspace,
)
from csttool.runtime_protocol import CompletionStatus, Task, new_session_id
from test.cst_integration_support import (
    cst_processes,
    force_cleanup,
    wait_completion_or_controller_exit,
    wait_for_standard_exit,
    windows_process_snapshot,
)


pytestmark = pytest.mark.integration
RESULT_NAME = "Frequency (Multiple Modes)/Mode 1"


def _read_runtime_scalar(path):
    values = VBPostProcessor.readFile(path)
    assert values is not None
    return float(values["value"]), values


def test_hom_runtime_r_over_q_uses_solved_fields_without_parameter_update(
    cst_executable,
):
    source = (
        Path(__file__).parent.parent
        / "project"
        / "HOM analysis"
        / "HOM analysis_clean.cst"
    )
    root = Path.cwd() / ".pytest_cache" / "cst-p5-5" / new_session_id()[:8]
    session_id = new_session_id()
    task = Task.create(session_id, {"fmin": "720", "fmax": "800"})
    workspace = prepare_hom_runtime_postprocess_workspace(
        root, task, source, result_name=RESULT_NAME
    )
    worker = workspace.worker
    baseline = cst_processes(windows_process_snapshot())
    with (root / "cst-p5-5.log").open("wb") as log:
        process = subprocess.Popen(
            [str(cst_executable), "-m", str(worker.macro_path)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        forced = {}
        try:
            completion = wait_completion_or_controller_exit(
                worker, task, process, timeout=1800
            )
            assert completion.status is CompletionStatus.SUCCESS, completion
            native = read_hom_native_results(worker.snapshot_path.with_suffix(""))
            runtime_5mm, metadata_5mm = _read_runtime_scalar(
                workspace.r_over_q_5mm_path
            )
            runtime_7_5mm, metadata_7_5mm = _read_runtime_scalar(
                workspace.r_over_q_7_5mm_path
            )
            assert runtime_5mm == pytest.approx(
                native["r_over_q_offset_5mm"].value, rel=1e-6, abs=1e-9
            )
            assert math.isfinite(runtime_7_5mm)
            assert float(metadata_5mm["yoffset"]) == 5.0
            assert float(metadata_7_5mm["yoffset"]) == 7.5
            (root / "report.json").write_text(
                json.dumps(
                    {
                        "native_r_over_q_5mm": native[
                            "r_over_q_offset_5mm"
                        ].value,
                        "runtime_r_over_q_5mm": runtime_5mm,
                        "runtime_r_over_q_7_5mm": runtime_7_5mm,
                        "post_solve_parameter_update": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
                newline="\n",
            )
            worker.protocol.acknowledge(completion)
            wait_for_standard_exit(process, baseline, timeout=120)
        finally:
            forced = force_cleanup(process, baseline)
    assert not forced, f"P5.5 worker required forced cleanup: {forced}"
