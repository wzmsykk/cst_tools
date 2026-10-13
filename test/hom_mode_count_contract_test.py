from pathlib import Path

import pytest

from test.managed_hom_ten_modes_fault_resume_integration_test import (
    _config, _dispatch_next_without_controller, _run_next, _single_mode_parameters,
)
from csttool.runtime_protocol import new_session_id


def test_ten_mode_scan_requests_one_mode_per_solve(tmp_path, monkeypatch):
    import test.managed_hom_ten_modes_fault_resume_integration_test as scan

    calls = []

    class Worker:
        session_id = new_session_id()
        log_path = tmp_path / "worker.log"
        marker_path = tmp_path / "worker.marker"
        task_path = tmp_path / "input.task"

        def run_task(self, name, *, params):
            calls.append(params)
            return params

    worker = Worker()
    worker.log_path.touch()
    monkeypatch.setattr(scan, "_result_values", lambda result: result)
    assert _run_next(worker, 720) == _single_mode_parameters(720)
    task, _ = _dispatch_next_without_controller(worker, 800)
    assert {p.name: p.value for p in task.parameters}["nmodes"] == "1"
    assert calls == [{"nmodes": 1, "fmin": 720, "fmax": 770.0}]
    config = _config(tmp_path, "0", Path("CST.exe"))
    assert {p["name"] for p in config["paramList"]} == {"nmodes", "fmin", "fmax"}


@pytest.mark.parametrize("template", [
    "runtime_managed_worker_v1_main.vb",
    "runtime_worker_v1_main.vb",
    "runtime_warm_worker_v1_main.vb",
])
def test_worker_applies_explicit_mode_count_after_rebuild_before_solve(template):
    source = (Path(__file__).parents[1] / "data" / template).read_text(encoding="utf-8")
    rebuild = source.index("rebuilt = Rebuild")
    binding = source.index('EigenmodeSolver.SetNumberOfModes CInt(requestedModes)')
    solve = source.index("EigenmodeSolver.Start")
    assert rebuild < binding < solve
    assert 'If LCase(task.Parameters(i).Name) = "nmodes" Then' in source
