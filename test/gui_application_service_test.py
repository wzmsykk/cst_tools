import logging

import pytest

from GUI.application_service import CstApplicationService, RunRequest
from csttool.application_backend import CstApplicationBackend


class ModernBackend:
    supports_cst_backend_selection = True

    def __init__(self):
        self.logger = logging.getLogger("modern-service-test")
        self.calls = []

    def select_project_directory(self, value): self.calls.append(("project", value))
    def select_cst_file(self, value): self.calls.append(("cst", value))
    def get_cst_installations(self): return ("2025",)
    def get_selected_cst_installation(self): return "2025"
    def select_cst_installation(self, version, executable): return version, executable
    def get_postprocess_settings(self): return [{"resultName": "frequency"}]
    def update_postprocess_settings(self, value): self.calls.append(("pps", value))
    def get_algorithm_settings(self): return {"fmin": 500}
    def update_algorithm_settings(self, value): self.calls.append(("algorithm", value))
    def initialize_run(self, resume, worker_count): self.calls.append(("initialize", resume, worker_count))
    def prepare_run(self): self.calls.append(("prepare",))
    def execute_run(self): self.calls.append(("execute",)); return "done"
    def request_stop(self): self.calls.append(("stop",))
    def recover_project_sessions(self): return []
    def get_recovery_sessions(self): return ()
    def is_recovery_required(self): return False
    def add_progress_listener(self, listener): self.listener = listener


def test_application_service_forwards_modern_backend_operations():
    backend = ModernBackend()
    service = CstApplicationService(backend)
    service.select_project_directory("project")
    service.select_cst_file("input.cst")
    service.update_algorithm_settings({"fmin": 600})
    service.update_postprocess_settings([])
    service.initialize_run(RunRequest(True, 3))
    service.prepare_run()
    assert service.execute_run() == "done"
    service.request_stop()
    assert ("initialize", True, 3) in backend.calls
    assert backend.calls[-2:] == [("execute",), ("stop",)]


def test_run_request_rejects_invalid_worker_count():
    with pytest.raises(ValueError, match="at least 1"):
        RunRequest(False, 0)


def test_application_service_requires_modern_backend_contract():
    class OldBackend:
        logger = logging.getLogger("old-backend")

    with pytest.raises(TypeError, match="ApplicationBackend"):
        CstApplicationService(OldBackend())


def test_default_service_uses_application_backend(monkeypatch):
    backend = object.__new__(CstApplicationBackend)
    backend.logger = logging.getLogger("new-backend-test")
    monkeypatch.setattr("GUI.application_service.CstApplicationBackend", lambda: backend)
    assert CstApplicationService().backend is backend
