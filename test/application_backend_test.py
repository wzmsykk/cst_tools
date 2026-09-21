import logging

import pytest

from csttool.application_backend import (
    BackendInitializationError,
    BackendLifecycleError,
    BackendPreparationError,
    BackendState,
    CstApplicationBackend,
)
from csttool.runtime_protocol import FileProtocol, new_session_id
from csttool.project_run_lock import ProjectRunLock


class FakeGlobalConfig:
    def __init__(self, checks=(True,)):
        self.checks = list(checks)
        self.saved = 0
        self.installations = []
        self.selected_installation = None

    def checkCSTENVConfig(self):
        return self.checks.pop(0)

    def saveconf(self):
        self.saved += 1

    def printconf(self):
        pass

    def list_cst_installations(self):
        return tuple(self.installations)

    def get_selected_cst_installation(self):
        return self.selected_installation

    def select_cst_installation(self, version, executable):
        self.selected_installation = (version, executable)
        return self.selected_installation


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

    def prepareProject(self, resume):
        self.prepared_with = resume
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

    def set_resume(self, resume):
        self.resume = bool(resume)

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

    backend.initialize_run(True, 1)
    assert backend.state is BackendState.INITIALIZED
    backend.prepare_run()
    assert backend.state is BackendState.PREPARED
    assert manager_calls[0]["maxTask"] == 1

    assert backend.execute_run() == "completed"
    assert backend.state is BackendState.STOPPED
    assert backend.jm is None
    assert manager.stop_count == 1
    assert global_config.saved == 1
    assert project.prepared_with is True


def test_backend_rejects_invalid_operation_order():
    backend, *_ = make_backend()

    with pytest.raises(BackendLifecycleError, match="execute run"):
        backend.execute_run()

    backend.initialize_run(False, 1)
    with pytest.raises(BackendLifecycleError, match="initialize run"):
        backend.initialize_run(False, 1)
    with pytest.raises(BackendLifecycleError, match="update algorithm"):
        backend.update_algorithm_settings({"fmin": 600})


def test_backend_accepts_multiple_workers_when_explicitly_requested():
    backend, *_ = make_backend()

    backend.initialize_run(False, 2)

    assert backend.worker_count == 2


def test_backend_switches_cst_only_while_configurable():
    backend, global_config, *_ = make_backend()

    assert backend.select_cst_installation(2025, "cst.exe") == (2025, "cst.exe")
    assert global_config.selected_installation == (2025, "cst.exe")

    backend.initialize_run(False, 1)
    with pytest.raises(BackendLifecycleError, match="select CST installation"):
        backend.select_cst_installation(2022, "old.exe")


def test_backend_can_retry_after_initialization_failure():
    backend, *_ = make_backend(checks=(False, True))

    with pytest.raises(BackendInitializationError):
        backend.initialize_run(False, 1)
    assert backend.state is BackendState.FAILED

    backend.initialize_run(False, 1)
    assert backend.state is BackendState.INITIALIZED


def test_algorithm_failure_still_stops_and_clears_manager():
    algorithm = FakeAlgorithm(RuntimeError("solver failed"))
    backend, _, project, manager, _ = make_backend(algorithm=algorithm)
    backend.select_project_directory("project")
    backend.initialize_run(False, 1)
    backend.prepare_run()

    with pytest.raises(RuntimeError, match="solver failed"):
        backend.execute_run()

    assert backend.state is BackendState.FAILED
    assert backend.jm is None
    assert manager.stop_count == 1
    assert len(project.statuses) == 2


def test_stop_request_is_idempotent_with_execution_cleanup(tmp_path):
    backend, *_rest, manager, _calls = make_backend()
    backend.select_project_directory(tmp_path)
    backend.initialize_run(False, 1)
    backend.prepare_run()
    backend._set_state(BackendState.RUNNING)

    backend.request_stop()
    backend.request_stop()
    backend._stop_manager_once()

    assert backend.state is BackendState.STOPPING
    assert manager.stop_count == 1


def test_prepare_detects_unclosed_managed_session(tmp_path):
    backend, _global, project, manager, _calls = make_backend()
    project.currProjectDir = tmp_path
    session_id = new_session_id()
    session_root = tmp_path / "temp" / "worker_0" / session_id
    FileProtocol(session_root / "protocol")
    (session_root / "worker.state").write_text("ready", encoding="ascii")
    backend.initialize_run(False, 1)

    with pytest.raises(BackendPreparationError, match="未闭合 CST 会话"):
        backend.prepare_run()

    assert backend.state is BackendState.RECOVERY_REQUIRED
    assert manager.stop_count == 0
    assert ProjectRunLock.active_owner(tmp_path) is None


def test_two_backend_instances_cannot_submit_the_same_project(tmp_path):
    first, *_ = make_backend()
    second, *_ = make_backend(checks=(True, True))
    first.select_project_directory(tmp_path)
    second.select_project_directory(tmp_path)

    first.initialize_run(False, 1)
    first.prepare_run()
    second.initialize_run(False, 1)

    assert second.get_recovery_sessions() == []
    with pytest.raises(BackendPreparationError, match="另一个窗口"):
        second.prepare_run()

    assert first.execute_run() == "completed"
    assert ProjectRunLock.active_owner(tmp_path) is None

    second.initialize_run(False, 1)
    second.prepare_run()
    assert second.execute_run() == "completed"


def test_recovery_cannot_stop_a_run_owned_by_another_window(tmp_path):
    first, *_ = make_backend()
    second, *_ = make_backend()
    first.select_project_directory(tmp_path)
    second.select_project_directory(tmp_path)
    first.initialize_run(False, 1)
    first.prepare_run()

    with pytest.raises(BackendLifecycleError, match="另一个窗口"):
        second.recover_project_sessions()

    first.execute_run()


def test_backend_progress_listener_failures_do_not_break_worker_updates():
    backend, *_ = make_backend()
    observed = []
    backend.add_progress_listener(observed.append)
    backend.add_progress_listener(lambda _event: (_ for _ in ()).throw(RuntimeError("ui")))

    backend._publish_cst_progress("progress")

    assert observed == ["progress"]


def test_successful_recovery_persists_interrupted_project_state(tmp_path):
    backend, _global, project, *_ = make_backend()
    project.currProjectDir = tmp_path
    backend._set_state(BackendState.RECOVERY_REQUIRED)

    assert backend.recover_project_sessions() == []

    assert backend.state is BackendState.INTERRUPTED
    assert project.statuses[-1].name == "INTERRUPTED"
