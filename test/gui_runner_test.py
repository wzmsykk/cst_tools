"""Qt client behavior through an in-process transport double, not CST."""
import logging
import os
import time
from uuid import uuid4
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QCloseEvent
from GUI.application_service import ConfigurationService
from GUI.main_window import MainWindow
from GUI.runner_backend import RunnerBackend
from GUI.runner_controller import RunnerController
from GUI.run_controller import RunState


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


class Client:
    def __init__(self, project):
        self.project = project
        self.ops = []
        self.state = 'IDLE'
        self.fail = False
    def connect(self, **kwargs):
        if self.fail:
            raise OSError('test disconnected')
        return {'instance_id': 'test-runner', 'run_id': 'run', 'state': self.state,
                'project': self.project, 'phase': 'running', 'error': None}
    def events(self, cursor=0):
        return {'cursor': 0, 'events': []}
    def pending_stop_request(self):
        return getattr(self, 'stop_request', None)
    def save_stop_request(self, request_id):
        self.stop_request = request_id
    def clear_stop_request(self, request_id):
        self.stop_request = None
    def command(self, op, *args, **kwargs):
        self.ops.append(op)
        if op == 'start':
            self.state = 'RUNNING'
        if op in ('stop', 'cancel_start'):
            self.state = 'INTERRUPTED'


def wait(app, predicate):
    end = time.monotonic() + 4
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Qt client condition timed out')


def test_persisted_recovery_gate_keeps_gui_recovery_entry(app, tmp_path):
    from csttool.runner import Runner
    from test.project_recovery_state_test import real_project_backend
    real_project_backend(tmp_path)
    runner = Runner(tmp_path)
    backend = RunnerBackend()
    backend.select_project_directory(str(tmp_path))
    class SnapshotClient(Client):
        def connect(self, **kwargs):
            return runner.snapshot()
    backend.client = SnapshotClient(backend.project)
    controller = RunnerController(ConfigurationService(backend))
    try:
        controller.set_inputs_ready(True)
        wait(app, lambda: controller.state is RunState.RECOVERY_REQUIRED)
        assert controller.recovery_count == 1
        assert runner.snapshot()['project_task_status'] == 'RECOVERY_REQUIRED'
    finally:
        controller.detach()
        runner.close()


def test_gui_dispatch_is_async_reconnect_does_not_resubmit(app, tmp_path):
    backend = RunnerBackend()
    backend.select_project_directory(str(tmp_path))
    client = backend.client = Client(backend.project)
    controller = RunnerController(ConfigurationService(backend))
    controller.set_inputs_ready(True)
    try:
        assert controller.start(False, 1)
        wait(app, lambda: controller.state is RunState.RUNNING and 'start' in client.ops)
        client.fail = True
        wait(app, lambda: controller.unknown)
        assert controller.has_active_work
        client.fail = False
        wait(app, lambda: not controller.unknown)
        assert client.ops.count('start') == 1
        assert controller.request_stop()
        wait(app, lambda: controller.state is RunState.READY and not controller.has_active_work)
    finally:
        controller.detach()


def test_production_window_can_detach_without_stopping(app, tmp_path, monkeypatch):
    backend = RunnerBackend()
    backend.supports_cst_backend_selection = False
    backend.select_project_directory(str(tmp_path))
    client = backend.client = Client(backend.project)
    client.state = 'RUNNING'
    window = MainWindow(engine=backend)
    monkeypatch.setattr(window, '_runner_close_choice', lambda: 'detach')
    wait(app, lambda: window.controller.state is RunState.RUNNING)
    assert window.claimControlButton.text() == '申请控制权'
    assert window.claimControlButton.isEnabled()
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert 'stop' not in client.ops
    assert window.controller.closed


def test_stop_while_start_command_is_pending_is_delivered_after_acceptance(app, tmp_path):
    backend = RunnerBackend()
    backend.select_project_directory(str(tmp_path))
    client = backend.client = Client(backend.project)
    controller = RunnerController(ConfigurationService(backend))
    controller.set_inputs_ready(True)
    try:
        assert controller.start(False, 1)
        assert controller.request_stop()
        wait(app, lambda: 'cancel_start' in client.ops)
        assert client.ops.count('start') == 1
        assert client.ops.index('cancel_start') > client.ops.index('start')
    finally:
        controller.detach()
