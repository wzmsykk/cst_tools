import json
import subprocess
from pathlib import Path

import pytest

from csttool.protocol_hom_template_evaluation import (
    prepare_hom_template_evaluation_workspace,
    read_result_template_inventory,
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
FREQUENCY_TEMPLATE_NAME = "Frequency (Multiple Modes)"


def _read_scalar(path):
    lines = path.read_text(encoding="ascii").splitlines()
    assert len(lines) == 1
    return float(lines[0])


def test_registered_templates_can_be_inventoried_and_evaluated_for_current_run(
    cst_executable,
):
    source = (
        Path(__file__).parent.parent
        / "project"
        / "HOM analysis"
        / "HOM analysis_clean.cst"
    )
    root = Path.cwd() / ".pytest_cache" / "cst-p5-6" / new_session_id()[:8]
    task = Task.create(new_session_id(), {"fmin": "720", "fmax": "800"})
    workspace = prepare_hom_template_evaluation_workspace(
        root, task, source, result_name=RESULT_NAME
    )
    worker = workspace.worker
    baseline = cst_processes(windows_process_snapshot())
    with (root / "cst-p5-6.log").open("wb") as log:
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
            before = read_result_template_inventory(workspace.inventory_before_path)
            after = read_result_template_inventory(workspace.inventory_after_path)
            assert before == after
            assert len(before) >= 5
            names = {record.result_name for record in before}
            assert FREQUENCY_TEMPLATE_NAME in names
            assert any("R over Q beta=1" in name for name in names)
            value_before = _read_scalar(workspace.result_before_path)
            value_after = _read_scalar(workspace.result_after_path)
            assert value_after == pytest.approx(value_before, rel=1e-12, abs=1e-12)
            (root / "report.json").write_text(
                json.dumps(
                    {
                        "registered_template_count": len(before),
                        "result_names": sorted(names),
                        "frequency_before_evaluate": value_before,
                        "frequency_after_evaluate": value_after,
                        "solver_calls": 1,
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
    assert not forced, f"P5.6 worker required forced cleanup: {forced}"
