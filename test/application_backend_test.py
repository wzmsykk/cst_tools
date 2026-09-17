import logging

import pytest

from base import cst_tools_main
from csttool.application_backend import (
    BackendInitializationError,
    BackendLifecycleError,
    BackendState,
    CstApplicationBackend,
)


class FakeGlobalConfig:
    def __init__(self, checks=(True,)):
        self.checks = list(checks)
        self.saved = 0

    def checkCSTENVConfig(self):
        return self.checks.pop(0)

    def saveconf(self):
        self.saved += 1

    def printconf(self):
        pass


class FakeProjectConfig:
    def __init__(self):
        self.currProjectDir = None
        self.currCSTFilePath = None
        self.pps = []
        self.ready = False
        self.statuses = []

    def readPPSListFromFile(self, path):
        return [{"resultName": "frequency"}]

    def setCurrPPSList(self, values):
        self.pps = values

    def getCurrPPSList(self):
        return self.pps

    def assignProjectDir(self, path):
        self.currProjectDir = path

    def assignInputCSTFilePath(self, path):
        self.currCSTFilePath = path

    def prepareProject(self, start_from_existing, safe_mode):
        self.prepared_with = (start_from_existing, safe_mode)
        self.ready = True

    def isReady(self):
        return self.ready

    def getParamsList(self):
        return [{"name": "fmin"}]

    def updateTaskStatus(self, status):
        self.statuses.append(status)


class FakeAlgorithm:
    def __init__(self, failure=None):
        self.failure = failure
        self.manager = None
        self.params = None

    def getEditableAttrs(self):
        return {"fmin": 500}

    def setEditableAttrs(self, values):
        self.attrs = values

    def setJobManager(self, manager):
        self.manager = manager

    def setCSTParams(self, params):
        self.params = params

    def start(self):
        if self.failure:
            raise self.failure
        return "completed"


class FakeManager:
    def __init__(self):
        self.stop_count = 0

    def stop(self):
        self.stop_count += 1


def make_backend(*, checks=(True,), algorithm=None):
    global_config = FakeGlobalConfig(checks)
    project_config = FakeProjectConfig()
    manager = FakeManager()
    manager_calls = []

    def manager_factory(**kwargs):
        manager_calls.append(kwargs)
        return manager

    backend = CstApplicationBackend(
        global_config_manager=global_config,
        project_config_manager=project_config,
        algorithm=algorithm or FakeAlgorithm(),
        manager_factory=manager_factory,
        application_logger=logging.getLogger("application-backend-test"),
    )
    return backend, global_config, project_config, manager, manager_calls


def test_backend_happy_path_has_explicit_lifecycle_and_cleanup():
    backend, global_config, project, manager, manager_calls = make_backend()
    backend.select_project_directory("project")
    backend.select_cst_file("model.cst")

    backend.initialize_run(True, False, 3)
    assert backend.state is BackendState.INITIALIZED
    backend.prepare_run()
    assert backend.state is BackendState.PREPARED
    assert manager_calls[0]["maxTask"] == 3

    assert backend.execute_run() == "completed"
    assert backend.state is BackendState.STOPPED
    assert backend.jm is None
    assert manager.stop_count == 1
    assert global_config.saved == 1
    assert project.prepared_with == (True, False)


def test_backend_rejects_invalid_operation_order():
    backend, *_ = make_backend()

    with pytest.raises(BackendLifecycleError, match="execute run"):
        backend.execute_run()

    backend.initialize_run(False, False, 1)
    with pytest.raises(BackendLifecycleError, match="initialize run"):
        backend.initialize_run(False, False, 1)
    with pytest.raises(BackendLifecycleError, match="update algorithm"):
        backend.update_algorithm_settings({"fmin": 600})


def test_backend_can_retry_after_initialization_failure():
    backend, *_ = make_backend(checks=(False, True))

    with pytest.raises(BackendInitializationError):
        backend.initialize_run(False, False, 1)
    assert backend.state is BackendState.FAILED

    backend.initialize_run(False, True, 2)
    assert backend.state is BackendState.INITIALIZED


def test_algorithm_failure_still_stops_and_clears_manager():
    algorithm = FakeAlgorithm(RuntimeError("solver failed"))
    backend, _, project, manager, _ = make_backend(algorithm=algorithm)
    backend.initialize_run(False, False, 1)
    backend.prepare_run()

    with pytest.raises(RuntimeError, match="solver failed"):
        backend.execute_run()

    assert backend.state is BackendState.FAILED
    assert backend.jm is None
    assert manager.stop_count == 1
    assert len(project.statuses) == 2


def test_stop_request_is_idempotent_with_execution_cleanup():
    backend, *_rest, manager, _calls = make_backend()
    backend.initialize_run(False, False, 1)
    backend.prepare_run()
    backend._set_state(BackendState.RUNNING)

    backend.request_stop()
    backend.request_stop()
    backend._stop_manager_once()

    assert backend.state is BackendState.STOPPING
    assert manager.stop_count == 1


def test_legacy_facade_translates_old_api_without_owning_execution_logic():
    global_config = FakeGlobalConfig()
    project_config = FakeProjectConfig()
    manager = FakeManager()
    application = cst_tools_main(
        global_config_manager=global_config,
        project_config_manager=project_config,
        algorithm=FakeAlgorithm(),
        manager_factory=lambda **kwargs: manager,
        application_logger=logging.getLogger("legacy-facade-test"),
    )

    application.setProjectDir("project")
    application.setCSTFilePath("model.cst")
    application.setFlags(True, False)
    application.setWorkerCount(2)

    assert application.wininit() is True
    assert application.setRunInfos() is None
    assert application.starttask() == "completed"
    assert application.state is BackendState.STOPPED
    assert manager.stop_count == 1
