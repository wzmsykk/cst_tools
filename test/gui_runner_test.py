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


def test_idle_snapshot_stays_busy_until_executor_disposal(app, tmp_path):
    backend = RunnerBackend()
    backend.select_project_directory(str(tmp_path))
    class SettlingClient(Client):
        active = True
        def connect(self, **kwargs):
            return dict(super().connect(**kwargs), execution_active=self.active)
    backend.client = SettlingClient(backend.project)
    controller = RunnerController(ConfigurationService(backend))
    controller.set_inputs_ready(True)
    try:
        wait(app, lambda: controller.state is RunState.STOPPING)
        assert controller.has_active_work
        assert not controller.start(False, 1)
        backend.client.active = False
        wait(app, lambda: controller.state is RunState.READY)
        assert not controller.has_active_work
    finally:
        controller.detach()


def wait(app, predicate):
    end = time.monotonic() + 4
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Qt client condition timed out')


def test_shutdown_stays_offline_until_explicit_connection(app, tmp_path, monkeypatch):
    backend = RunnerBackend()
    backend.select_project_directory(str(tmp_path))
    class ShutdownClient(Client):
        observations = 0
        def connect(self, **kwargs):
            self.observations += 1
            return super().connect(**kwargs)
        def shutdown_and_wait(self, **kwargs):
            self.ops.append('shutdown')
            return {'runner_stopped': True}
    client = backend.client = ShutdownClient(backend.project)
    controller = RunnerController(ConfigurationService(backend))
    try:
        wait(app, lambda: controller.instance is not None)
        assert controller.request_shutdown()
        wait(app, lambda: controller.runner_stopped)
        count = client.observations
        for _ in range(5):
            controller.poll()
        assert client.observations == count
        assert not controller.start()
        new_client = ShutdownClient(backend.project)
        monkeypatch.setattr(backend, 'select_project_directory', lambda path: setattr(backend, 'client', new_client))
        assert controller.connect_runner()
        wait(app, lambda: not controller.runner_stopped and controller.instance is not None)
        assert new_client.observations > 0
        assert not new_client.ops  # Connecting never submits a run.
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


@pytest.mark.parametrize('state,unknown,read_only', [
    (RunState.RUNNING, False, False), (RunState.RECOVERY_REQUIRED, False, False),
    (RunState.READY, True, False), (RunState.READY, False, True)])
def test_unsafe_runner_shutdown_is_not_sent(app, tmp_path, state, unknown, read_only):
    backend = RunnerBackend()
    backend.select_project_directory(str(tmp_path))
    client = backend.client = Client(backend.project)
    controller = RunnerController(ConfigurationService(backend))
    controller.timer.stop()
    controller.state, controller.unknown, controller.read_only = state, unknown, read_only
    try:
        assert not controller.request_shutdown()
        assert client.ops == []
    finally:
        controller.detach()
        controller.pool.shutdown(wait=True)


def test_runner_management_confirmation_and_legacy_identity(app, tmp_path, monkeypatch):
    backend = RunnerBackend()
    backend.supports_cst_backend_selection = False
    backend.select_project_directory(str(tmp_path))
    backend.client = Client(backend.project)
    window = MainWindow(engine=backend)
    try:
        wait(app, lambda: window.controller.instance is not None)
        window.showRunnerManagement()
        dialog = window._runner_dialog
        assert '旧版未提供身份' in dialog.details.toPlainText()
        assert '尚未采集' in dialog.details.toPlainText()
        from csttool.lifecycle_diagnostics import lifecycle_facts
        from csttool.session_closure import CloseEvidence, evaluate_closure
        from types import SimpleNamespace
        assessment = evaluate_closure(CloseEvidence('s', False, 0, stop_ack='valid', unresolved_completion=True))
        backend.runner_status['lifecycle'] = lifecycle_facts([SimpleNamespace(
            closure=assessment, worker_id='0', session_id='s', root=tmp_path)])
        dialog.refresh()
        assert 'completion-not-reconciled' in dialog.details.toPlainText()
        assert '标准收尾：已确认' in dialog.details.toPlainText()
        assert dialog.shutdownButton.isEnabled()
        calls = []
        monkeypatch.setattr(window, '_confirm_action', lambda *args: False)
        monkeypatch.setattr(window.controller, 'request_shutdown', lambda: calls.append('shutdown'))
        dialog.request_shutdown()
        assert calls == []
        monkeypatch.setattr(window, '_confirm_action', lambda *args: True)
        dialog.request_shutdown()
        assert calls == ['shutdown']
        window.controller.unknown = True
        dialog.refresh()
        assert not dialog.shutdownButton.isEnabled()
        window.controller.unknown = False
        window.controller.runner_stopped = True
        window.connectionLabelChanged('后台已退出')
        assert not window.StartButton.isEnabled()
        assert window.selectProjectDirButton.isEnabled()
    finally:
        window.controller.detach()
        window.controller.pool.shutdown(wait=True)
        window.close()


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
