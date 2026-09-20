from collections import deque
import logging
from pathlib import Path
from threading import Lock
from time import sleep

import pytest

from csttool.cstmanager import CSTManager
from csttool.pillbox_analytic import (
    PillboxRadiusBatchOptimizer,
    tm010_frequency_mhz,
    tm010_radius_mm,
)


class _GlobalConfig:
    def __init__(self, root: Path):
        self.conf = {
            "BASE": {"datadir": str(root / "data")},
            "CST": {"cstexepath": str(root / "cst.exe")},
        }


class _ProjectConfig:
    def __init__(self, root: Path):
        self.currProjectDir = root
        self.conf = {
            "DIRS": {"tempdir": "temp", "resultdir": "result"},
            "CST": {"CSTFilename": "Pillbox.cst"},
            "PROJECT": {"ProjectType": "pillbox-analytic"},
        }

    def getCurrPPSList(self):
        return []


class _AnalyticPillboxWorker:
    def __init__(self, worker_id, config, tracker):
        self.ID = worker_id
        self.source_project = Path(config["cstPath"])
        self.tracker = tracker
        self.stopped = False

    def runWithParam(self, resultname, *, params):
        with self.tracker["lock"]:
            self.tracker["active"] += 1
            self.tracker["peak"] = max(
                self.tracker["peak"], self.tracker["active"]
            )
        try:
            sleep(0.005)
            radius = float(params["R"])
            frequency = tm010_frequency_mhz(radius)
            with self.tracker["lock"]:
                self.tracker["radii"].append(radius)
            return {
                "TaskStatus": "Success",
                "FailureReport": None,
                "RunName": resultname,
                "RunParameters": dict(params),
                "PostProcessResult": [
                    {"resultName": "frequency", "value": frequency}
                ],
            }
        finally:
            with self.tracker["lock"]:
                self.tracker["active"] -= 1

    def stop(self):
        self.stopped = True


def test_standard_manager_batch_optimizes_pillbox_radius_to_500_mhz(tmp_path):
    tracker = {"active": 0, "peak": 0, "radii": [], "lock": Lock()}
    workers = []
    worker_sources = deque()

    def worker_factory(worker_id, config, _logger):
        worker_sources.append(Path(config["cstPath"]).resolve())
        worker = _AnalyticPillboxWorker(worker_id, config, tracker)
        workers.append(worker)
        return worker

    manager = CSTManager(
        _GlobalConfig(tmp_path),
        _ProjectConfig(tmp_path),
        params=[{"name": "R", "type": "double"}],
        logger=logging.getLogger("pillbox-analytic-batch"),
        maxTask=4,
        worker_factory=worker_factory,
        max_jobs_per_worker=4,
    )
    try:
        result = PillboxRadiusBatchOptimizer(
            manager,
            target_frequency_mhz=500.0,
            radius_bounds_mm=(180.0, 280.0),
        ).optimize()
    finally:
        manager.stop()

    analytic_radius = tm010_radius_mm(500.0)
    assert analytic_radius == pytest.approx(229.48505567042014)
    assert result.best.radius_mm == pytest.approx(analytic_radius, abs=0.01)
    assert result.best.frequency_mhz == pytest.approx(500.0, abs=0.02)
    assert result.best.target_error_mhz <= 0.02
    assert result.evaluations >= 9
    assert tracker["peak"] > 1
    assert len(tracker["radii"]) == result.evaluations
    assert all(
        source == (tmp_path / "Pillbox.cst").resolve()
        for source in worker_sources
    )
    assert manager.get_confirmed_snapshot() is None
    assert all(worker.stopped for worker in workers)


@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf")])
def test_pillbox_analytic_model_rejects_invalid_radius(invalid):
    with pytest.raises(ValueError, match="radius"):
        tm010_frequency_mhz(invalid)


class _FaultInjectingPillboxWorker(_AnalyticPillboxWorker):
    def runWithParam(self, resultname, *, params):
        radius = float(params["R"])
        key = round(radius, 9)
        with self.tracker["lock"]:
            attempt = self.tracker["attempts"].get(key, 0) + 1
            self.tracker["attempts"][key] = attempt
            fault = self.tracker["faults"].get(key)
            if fault in {"raise-once", "fail-once"} and attempt > 1:
                fault = None
        if fault == "raise-once":
            self.tracker["events"].append(("raised", key, attempt, self.ID))
            raise RuntimeError("injected worker process loss")
        if fault in {"fail-once", "fail-always"}:
            self.tracker["events"].append(("failed", key, attempt, self.ID))
            return {
                "TaskStatus": "Failure",
                "FailureReport": "injected solver failure",
                "RunName": resultname,
                "RunParameters": dict(params),
                "PostProcessResult": None,
            }
        self.tracker["events"].append(("success", key, attempt, self.ID))
        return super().runWithParam(resultname, params=params)


def _fault_test_manager(tmp_path, faults):
    tracker = {
        "active": 0,
        "peak": 0,
        "radii": [],
        "lock": Lock(),
        "attempts": {},
        "faults": dict(faults),
        "events": [],
        "sources": [],
        "workers": [],
    }

    def worker_factory(worker_id, config, _logger):
        tracker["sources"].append(Path(config["cstPath"]).resolve())
        worker = _FaultInjectingPillboxWorker(worker_id, config, tracker)
        tracker["workers"].append(worker)
        return worker

    manager = CSTManager(
        _GlobalConfig(tmp_path),
        _ProjectConfig(tmp_path),
        params=[{"name": "R", "type": "double"}],
        logger=logging.getLogger("pillbox-fault-batch"),
        maxTask=4,
        worker_factory=worker_factory,
        max_jobs_per_worker=100,
    )
    return manager, tracker


def test_standard_batch_recovers_worker_exception_and_solver_failure(tmp_path):
    manager, tracker = _fault_test_manager(
        tmp_path,
        {205.0: "raise-once", 242.5: "fail-once"},
    )
    try:
        result = PillboxRadiusBatchOptimizer(
            manager,
            target_frequency_mhz=500.0,
            radius_bounds_mm=(180.0, 280.0),
        ).optimize()
    finally:
        manager.stop()

    assert result.best.frequency_mhz == pytest.approx(500.0, abs=0.02)
    assert tracker["attempts"][205.0] == 2
    assert tracker["attempts"][242.5] >= 2
    assert any(event[:3] == ("raised", 205.0, 1) for event in tracker["events"])
    assert any(event[:3] == ("failed", 242.5, 1) for event in tracker["events"])
    assert any(event[:3] == ("success", 205.0, 2) for event in tracker["events"])
    assert any(event[:3] == ("success", 242.5, 2) for event in tracker["events"])
    assert len(tracker["workers"]) >= 6
    assert all(
        source == (tmp_path / "Pillbox.cst").resolve()
        for source in tracker["sources"]
    )
    assert manager.get_confirmed_snapshot() is None


def test_standard_batch_can_restart_after_retry_exhaustion(tmp_path):
    manager, tracker = _fault_test_manager(tmp_path, {230.0: "fail-always"})
    optimizer = PillboxRadiusBatchOptimizer(
        manager,
        target_frequency_mhz=500.0,
        radius_bounds_mm=(180.0, 280.0),
    )
    try:
        with pytest.raises(RuntimeError, match="injected solver failure"):
            optimizer.optimize()

        assert tracker["attempts"][230.0] == 2
        assert manager.ready
        tracker["faults"].clear()
        recovered = optimizer.optimize()
    finally:
        manager.stop()

    assert recovered.best.frequency_mhz == pytest.approx(500.0, abs=0.02)
    assert all(
        source == (tmp_path / "Pillbox.cst").resolve()
        for source in tracker["sources"]
    )
