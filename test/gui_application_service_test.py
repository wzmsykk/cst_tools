import logging

import pytest

from GUI.application_service import CstApplicationService, RunRequest
from csttool.application_backend import CstApplicationBackend


class LegacyEngine:
    def __init__(self):
        self.logger = logging.getLogger("legacy-service-test")
        self.calls = []
        self.wininit_result = True
        self.prepare_result = None

    def setProjectDir(self, value):
        self.calls.append(("project", value))

    def setCSTFilePath(self, value):
        self.calls.append(("cst", value))

    def getCurrPostProcessList(self):
        return [{"resultName": "frequency"}]

    def setCurrPostProcessList(self, value):
        self.calls.append(("pps", value))

    def getAlgAttrs(self):
        return {"fmin": 500}

    def setAlgAttrs(self, value):
        self.calls.append(("algorithm", value))

    def setFlags(self, start_from_existing, safe):
        self.calls.append(("flags", start_from_existing, safe))

    def setWorkerCount(self, value):
        self.calls.append(("workers", value))

    def wininit(self):
        self.calls.append(("initialize",))
        return self.wininit_result

    def setRunInfos(self):
        self.calls.append(("prepare",))
        return self.prepare_result

    def starttask(self):
        self.calls.append(("execute",))
        return "done"

    def request_stop(self):
        self.calls.append(("stop",))


def test_application_service_translates_gui_operations():
    engine = LegacyEngine()
    service = CstApplicationService(engine)
    service.select_project_directory("project")
    service.select_cst_file("input.cst")
    service.update_algorithm_settings({"fmin": 600})
    service.update_postprocess_settings([])
    request = RunRequest(True, True, 3)
    service.initialize_run(request)
    service.prepare_run()
    assert service.execute_run() == "done"
    service.request_stop()

    assert ("flags", True, True) in engine.calls
    assert ("workers", 3) in engine.calls
    assert engine.calls[-2:] == [("execute",), ("stop",)]


def test_application_service_normalizes_legacy_failure_values():
    engine = LegacyEngine()
    service = CstApplicationService(engine)
    engine.wininit_result = False
    with pytest.raises(RuntimeError, match="初始化失败"):
        service.initialize_run(RunRequest(False, False, 1))

    engine.wininit_result = True
    engine.prepare_result = 0
    with pytest.raises(RuntimeError, match="准备失败"):
        service.prepare_run()


def test_run_request_rejects_invalid_worker_count():
    with pytest.raises(ValueError, match="at least 1"):
        RunRequest(False, False, 0)


def test_default_service_uses_new_application_backend(monkeypatch):
    backend = object.__new__(CstApplicationBackend)
    backend.logger = logging.getLogger("new-backend-test")
    monkeypatch.setattr(
        "GUI.application_service.CstApplicationBackend", lambda: backend
    )

    service = CstApplicationService()

    assert service.backend is backend
