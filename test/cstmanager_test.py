from __future__ import annotations

from collections import deque
import logging
from pathlib import Path
from threading import Lock
from time import sleep

import pytest

from csttool.cstmanager import CSTManager, ManagerState, SimulationTask


class FakeGlobalConfig:
    def __init__(self, root: Path):
        self.conf = {
            "BASE": {"datadir": str(root / "data")},
            "CST": {"cstexepath": str(root / "cst.exe")},
        }


class FakeProjectConfig:
    def __init__(self, root: Path):
        self.currProjectDir = root
        self.conf = {
            "DIRS": {"tempdir": "temp", "resultdir": "result"},
            "CST": {"CSTFilename": "model.cst"},
            "PROJECT": {"ProjectType": "default"},
        }

    def getCurrPPSList(self):
        return []


class FakeWorker:
    def __init__(self, worker_id, tracker, outcomes):
        self.ID = worker_id
        self.tracker = tracker
        self.outcomes = outcomes
        self.stopped = False

    def runWithParam(self, resultname, *, params):
        with self.tracker["lock"]:
            self.tracker["active"] += 1
            self.tracker["peak"] = max(
                self.tracker["peak"], self.tracker["active"]
            )
        sleep(0.01)
        try:
            outcome = self.outcomes.popleft() if self.outcomes else "Success"
            if isinstance(outcome, Exception):
                raise outcome
            return {
                "TaskStatus": outcome,
                "RunName": resultname,
                "RunParameters": params,
                "PostProcessResult": None,
            }
        finally:
            with self.tracker["lock"]:
                self.tracker["active"] -= 1

    def stop(self):
        self.stopped = True


@pytest.fixture
def manager_factory(tmp_path):
    managers = []

    def create(*, workers=2, outcomes=(), max_jobs=10):
        tracker = {
            "active": 0,
            "peak": 0,
            "lock": Lock(),
            "created": [],
        }
        shared_outcomes = deque(outcomes)

        def worker_factory(worker_id, config, logger):
            worker = FakeWorker(worker_id, tracker, shared_outcomes)
            tracker["created"].append(worker)
            return worker

        manager = CSTManager(
            FakeGlobalConfig(tmp_path),
            FakeProjectConfig(tmp_path),
            params=[],
            logger=logging.getLogger("cstmanager-test"),
            maxTask=workers,
            worker_factory=worker_factory,
            max_jobs_per_worker=max_jobs,
        )
        managers.append(manager)
        return manager, tracker

    yield create

    for manager in managers:
        manager.stop()


def test_batch_runs_concurrently_and_returns_submission_order(manager_factory):
    manager, tracker = manager_factory(workers=2)
    tasks = [SimulationTask({"x": value}, f"job-{value}") for value in range(4)]

    results = manager.run_batch(tasks)

    assert [result["RunName"] for result in results] == [
        "job-0",
        "job-1",
        "job-2",
        "job-3",
    ]
    assert tracker["peak"] == 2
    assert manager.state is ManagerState.IDLE


def test_failed_task_restarts_worker_and_retries(manager_factory):
    manager, tracker = manager_factory(workers=1, outcomes=["Failure", "Success"])

    result = manager.runWithParam({"x": 1}, "retry-me", retry_cnt=1)

    assert result["TaskStatus"] == "Success"
    assert len(tracker["created"]) == 2
    assert tracker["created"][0].stopped


def test_worker_is_recycled_after_job_limit(manager_factory):
    manager, tracker = manager_factory(workers=1, max_jobs=1)

    results = manager.run_batch(
        [SimulationTask({"x": 1}, "first"), SimulationTask({"x": 2}, "second")]
    )

    assert len(results) == 2
    assert len(tracker["created"]) == 2
    assert tracker["created"][0].stopped


def test_get_first_result_preserves_remaining_result_order(manager_factory):
    manager, _ = manager_factory(workers=2)
    for value in range(3):
        manager.addTask({"x": value}, f"job-{value}")
    manager.startProcessing()

    first = manager.getFirstResult()
    remaining = manager.getFullResults()

    assert first["RunName"] == "job-0"
    assert [result["RunName"] for result in remaining] == ["job-1", "job-2"]


def test_context_manager_stops_every_worker(manager_factory):
    manager, tracker = manager_factory(workers=2)

    manager.stop()

    assert manager.state is ManagerState.CLOSED
    assert all(worker.stopped for worker in tracker["created"])
    with pytest.raises(RuntimeError, match="closed"):
        manager.submit(SimulationTask({}, "late-task"))


def test_invalid_configuration_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="maxTask"):
        CSTManager(
            FakeGlobalConfig(tmp_path),
            FakeProjectConfig(tmp_path),
            params=[],
            maxTask=0,
        )
