from __future__ import annotations

from collections import deque
import logging
from pathlib import Path
from threading import Event, Lock, Thread
from time import sleep

import pytest

from csttool.configuration import CstBackendSettings, GlobalSettings, ProjectSettings
from csttool.cstmanager import CSTManager, ManagerState, SimulationTask


class FakeGlobalConfig:
    def __init__(self, root: Path):
        self.settings = GlobalSettings().with_cst("2022", str(root / "cst.exe"))


class FakeProjectConfig:
    def __init__(self, root: Path):
        self.currProjectDir = root
        self.settings = ProjectSettings(name="test-project", cst_filename=Path("model.cst"))

    def get_postprocess_settings(self):
        return []


class FakeWorker:
    def __init__(self, worker_id, tracker, outcomes):
        self.ID = worker_id
        self.tracker = tracker
        self.outcomes = outcomes
        self.stopped = False

    def run_task(self, resultname, *, params):
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
            "configs": [],
        }
        shared_outcomes = deque(outcomes)

        def worker_factory(worker_id, config, logger):
            worker = FakeWorker(worker_id, tracker, shared_outcomes)
            tracker["created"].append(worker)
            tracker["configs"].append(config)
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


def test_failed_task_restarts_worker_and_retries(manager_factory, caplog):
    caplog.set_level(logging.INFO)
    manager, tracker = manager_factory(workers=1, outcomes=["Failure", "Success"])

    result = manager.execute(
        SimulationTask({"x": 1}, "retry-me", retry_count=1)
    )

    assert result["TaskStatus"] == "Success"
    assert len(tracker["created"]) == 2
    assert tracker["created"][0].stopped
    messages = [record.getMessage() for record in caplog.records]
    start = next(i for i, message in enumerate(messages) if "WORKER_RESTART_START" in message)
    done = next(i for i, message in enumerate(messages) if "WORKER_RESTART_DONE" in message)
    success = next(i for i, message in enumerate(messages) if "TASK_DONE" in message and "status=Success" in message)
    assert start < done < success
    assert len({record.run_id for record in caplog.records if hasattr(record, "run_id")}) == 1


def test_hom_opt_in_can_retire_verified_failed_worker_and_retry_from_base(manager_factory):
    manager, tracker = manager_factory(workers=1, outcomes=['Failure', 'Success'])
    first = tracker['created'][0]
    original_stop = first.stop
    called = []
    first.stop = lambda: (_ for _ in ()).throw(RuntimeError('exit 1'))
    first.retire_failed_session = lambda: called.append(True) or True
    try:
        result = manager.execute(SimulationTask({}, 'hom', retry_count=1,
            continue_from_snapshot=True, retire_failed_session=True))
        assert result['TaskStatus'] == 'Success' and called == [True]
        assert tracker['configs'][1].project_path == Path(manager.cstProjPath)
    finally:
        first.stop = original_stop


def test_standard_task_does_not_opt_into_failed_retirement(manager_factory):
    manager, tracker = manager_factory(workers=1, outcomes=['Failure'])
    first = tracker['created'][0]
    original_stop = first.stop
    first.stop = lambda: (_ for _ in ()).throw(RuntimeError('exit 1'))
    first.retire_failed_session = lambda: pytest.fail('standard task may not auto-retire')
    try:
        with pytest.raises(RuntimeError, match='drain failed'):
            manager.execute(SimulationTask({}, 'standard'))
        assert len(tracker['created']) == 1
    finally:
        first.stop = original_stop


def test_worker_is_recycled_after_job_limit(manager_factory):
    manager, tracker = manager_factory(workers=1, max_jobs=1)

    results = manager.run_batch(
        [SimulationTask({"x": 1}, "first"), SimulationTask({"x": 2}, "second")]
    )

    assert len(results) == 2
    assert len(tracker["created"]) == 2
    assert tracker["created"][0].stopped


def test_worker_recycle_uses_its_last_confirmed_project_snapshot(tmp_path):
    created = []
    configs = []
    snapshot = tmp_path / "result" / "task-1" / "project.cst"

    class SnapshotWorker:
        def __init__(self, worker_id):
            self.ID = worker_id
            self.stopped = False

        def run_task(self, resultname, *, params):
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(b"confirmed")
            return {
                "TaskStatus": "Success",
                "RunName": resultname,
                "RunParameters": params,
                "PostProcessResult": [],
                "ProjectSnapshot": str(snapshot),
            }

        def stop(self):
            self.stopped = True

    def worker_factory(worker_id, config, _logger):
        configs.append(config)
        worker = SnapshotWorker(worker_id)
        created.append(worker)
        return worker

    manager = CSTManager(
        FakeGlobalConfig(tmp_path),
        FakeProjectConfig(tmp_path),
        params=[],
        maxTask=1,
        worker_factory=worker_factory,
        max_jobs_per_worker=1,
    )
    try:
        manager.run_batch(
            [
                SimulationTask({}, "mode-8", continue_from_snapshot=True),
                SimulationTask({}, "mode-9", continue_from_snapshot=True),
            ]
        )

        assert len(created) == 2
        assert created[0].stopped
        assert Path(configs[1].project_path) == snapshot.resolve()
        assert manager.get_confirmed_snapshot() == snapshot.resolve()
    finally:
        manager.stop()


def test_standard_batch_recycle_starts_from_base_project(tmp_path):
    configs = []
    snapshot = tmp_path / "result" / "task-1" / "project.cst"

    class SnapshotWorker(FakeWorker):
        def run_task(self, resultname, *, params):
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(b"independent-task-snapshot")
            result = super().run_task(resultname, params=params)
            result["ProjectSnapshot"] = str(snapshot)
            return result

    def worker_factory(worker_id, config, _logger):
        configs.append(config)
        return SnapshotWorker(
            worker_id,
            {"lock": Lock(), "active": 0, "peak": 0},
            deque(),
        )

    manager = CSTManager(
        FakeGlobalConfig(tmp_path),
        FakeProjectConfig(tmp_path),
        params=[],
        maxTask=1,
        worker_factory=worker_factory,
        max_jobs_per_worker=1,
    )
    try:
        manager.run_batch(
            [SimulationTask({"x": 1}, "first"), SimulationTask({"x": 2}, "second")]
        )

        assert len(configs) == 2
        assert Path(configs[1].project_path) == (tmp_path / "model.cst").resolve()
        assert manager.get_confirmed_snapshot() is None
    finally:
        manager.stop()


def test_explicit_snapshot_restore_rebuilds_idle_worker_pool(tmp_path):
    created = []
    configs = []
    snapshot = tmp_path / "result" / "mode-8" / "project.cst"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"confirmed")

    def worker_factory(worker_id, config, _logger):
        configs.append(config)
        worker = FakeWorker(
            worker_id,
            {"lock": Lock(), "active": 0, "peak": 0},
            deque(),
        )
        created.append(worker)
        return worker

    manager = CSTManager(
        FakeGlobalConfig(tmp_path),
        FakeProjectConfig(tmp_path),
        params=[],
        maxTask=2,
        worker_factory=worker_factory,
    )
    try:
        manager.restore_project_snapshot(snapshot)

        assert len(created) == 4
        assert all(worker.stopped for worker in created[:2])
        assert all(
            Path(config.project_path) == snapshot.resolve() for config in configs[2:]
        )
    finally:
        manager.stop()


def test_run_batch_preserves_result_order(manager_factory):
    manager, _ = manager_factory(workers=2)
    results = manager.run_batch(
        [SimulationTask({"x": value}, f"job-{value}") for value in range(3)]
    )

    assert [result["RunName"] for result in results] == [
        "job-0",
        "job-1",
        "job-2",
    ]


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
            worker_factory=lambda *_args: None,
        )


def test_production_configuration_drives_worker_and_manifest(tmp_path):
    from csttool.globalconfmanager import GlobalConfigManager
    from csttool.projectconfmanager import ProjectConfigManager
    from csttool.configuration import ProjectDirectorySettings, write_ini_atomic
    from csttool.hom_run_manifest import HomRunManifest
    from csttool.hom_scan import ScanPolicy

    global_config = GlobalConfigManager(tmp_path / "config" / "current.ini")
    global_config.settings = GlobalSettings(cst=CstBackendSettings("2025", tmp_path / "cst.exe"))
    project = tmp_path / "project"
    project.mkdir()
    (project / "model.cst").write_bytes(b"prepared")
    (project / "params.json").write_text("[]", encoding="utf-8")
    (project / "pps.json").write_text("[]", encoding="utf-8")
    project_config = ProjectConfigManager(global_config)
    project_config.select_project_directory(project)
    settings = ProjectSettings(
        name="production", cst_filename=Path("model.cst"),
        project_digest=project_config.file_digest(project / "model.cst"),
        directories=ProjectDirectorySettings(temp=Path("custom-temp"), result=Path("custom-result")),
    )
    write_ini_atomic(project / "project.ini", settings.to_parser())
    assert project_config.prepare_project(startFromExisted=True)
    configs = []

    class Worker:
        def stop(self):
            pass

    def factory(worker_id, config, logger):
        configs.append(config)
        return Worker()

    with CSTManager(global_config, project_config, params=[], worker_factory=factory) as manager:
        manifest = HomRunManifest.create(manager, ScanPolicy(500, 550, 1000))
        assert not hasattr(manager, "gconf")
        assert not hasattr(manager, "pconf")
        assert manifest.cst_version == "2025"
        assert manifest.cst_executable == str(tmp_path / "cst.exe")
        assert str(configs[0].executable) == manifest.cst_executable
        assert configs[0].project_path == project / "model.cst"
        assert configs[0].result_directory == project / "custom-result"
        assert configs[0].task_directory.parent == project / "custom-temp"


def test_stop_request_prevents_worker_rotation_and_new_dispatch(tmp_path):
    entered = Event()
    release = Event()
    created = []

    class BlockingWorker(FakeWorker):
        def run_task(self, resultname, *, params):
            entered.set()
            assert release.wait(5)
            return {
                "TaskStatus": "Success",
                "RunName": resultname,
                "RunParameters": params,
                "PostProcessResult": None,
            }

    def worker_factory(worker_id, _config, _logger):
        worker = BlockingWorker(
            worker_id,
            {"lock": Lock(), "active": 0, "peak": 0},
            deque(),
        )
        created.append(worker)
        return worker

    manager = CSTManager(
        FakeGlobalConfig(tmp_path),
        FakeProjectConfig(tmp_path),
        params=[],
        maxTask=1,
        max_jobs_per_worker=1,
        worker_factory=worker_factory,
    )
    results = []
    thread = Thread(
        target=lambda: results.extend(
            manager.run_batch(
                [SimulationTask({}, "active"), SimulationTask({}, "must-not-run")]
            )
        )
    )
    thread.start()
    assert entered.wait(2)

    manager.request_stop()
    assert manager.stop_requested
    assert not created[0].stopped
    release.set()
    thread.join(5)

    assert not thread.is_alive()
    assert [item["RunName"] for item in results] == ["active"]
    assert len(created) == 1
    manager.stop()
from csttool.configuration import GlobalSettings, ProjectSettings


def test_failed_hom_retry_uses_preprocessed_base_and_preserves_confirmed_snapshot(manager_factory, tmp_path):
    manager, tracker = manager_factory(workers=1, outcomes=['Failure', 'Success'])
    snapshot = tmp_path / 'last-confirmed.cst'
    snapshot.write_bytes(b'confirmed results must survive')
    slot = manager._slots[0]
    slot.confirmed_snapshot = snapshot
    manager._confirmed_snapshot = snapshot
    result = manager.execute(SimulationTask({'fmin': 1165.82, 'fmax': 1215.82},
        'retry-hom', retry_count=1, continue_from_snapshot=True))
    assert result['TaskStatus'] == 'Success'
    assert tracker['created'][0].stopped
    assert len(tracker['created']) == 2
    assert tracker['configs'][1].project_path == Path(manager.cstProjPath)
    assert tracker['configs'][1].project_path != snapshot
    assert snapshot.read_bytes() == b'confirmed results must survive'
    assert manager.get_confirmed_snapshot() == snapshot
