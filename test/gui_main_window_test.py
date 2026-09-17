import logging
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication

from GUI.main_window import MainWindow
from GUI.run_controller import InvalidRunState, RunState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeDialog(QObject):
    _signal_done = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.values = {}
        self.items = []
        self.enabled = True

    def setDefaultValues(self, values):
        self.values = dict(values)

    def getValues(self):
        return dict(self.values)

    def setPPSList(self, items):
        self.items = list(items)

    def getPPSList(self):
        return list(self.items)

    def show(self):
        pass

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)

    def raise_(self):
        pass

    def activateWindow(self):
        pass


class FakeMainTool:
    def __init__(self):
        self.logger = logging.getLogger(f"gui-test-{id(self)}")
        self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG)
        self.project_dir = None
        self.cst_path = None
        self.start_count = 0
        self.wininit_result = True
        self.run_info_result = None
        self.run_gate = threading.Event()
        self.start_exception = None
        self.stop_count = 0
        self.stop_exception = None
        self.worker_count = None

    def getCurrPostProcessList(self):
        return []

    def getAlgAttrs(self):
        return {}

    def setProjectDir(self, path):
        self.project_dir = path

    def setCSTFilePath(self, path):
        self.cst_path = path

    def setFlags(self, ctn, safe):
        self.flags = (ctn, safe)

    def setWorkerCount(self, worker_count):
        self.worker_count = worker_count

    def wininit(self):
        return self.wininit_result

    def setRunInfos(self):
        return self.run_info_result

    def starttask(self):
        self.start_count += 1
        if self.start_exception is not None:
            raise self.start_exception
        assert self.run_gate.wait(3), "test backend was not released"

    def request_stop(self):
        self.stop_count += 1
        if self.stop_exception is not None:
            raise self.stop_exception
        self.run_gate.set()

    def setAlgAttrs(self, values):
        self.alg_values = values

    def setCurrPostProcessList(self, values):
        self.pps_values = values


def make_window(qapp):
    tool = FakeMainTool()
    window = MainWindow(tool, FakeDialog(), FakeDialog())
    return window, tool


def process_until(qapp, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Qt condition was not reached before timeout")


def choose_inputs(window, monkeypatch, tmp_path):
    project_dir = str(tmp_path)
    cst_path = str(tmp_path / "input.cst")
    monkeypatch.setattr(
        "GUI.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: project_dir,
    )
    monkeypatch.setattr(
        "GUI.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (cst_path, True),
    )
    window.read_dir()
    window.read_cst()


def test_start_requires_both_project_directory_and_cst_file(qapp, monkeypatch, tmp_path):
    window, tool = make_window(qapp)
    assert not window.StartButton.isEnabled()

    monkeypatch.setattr(
        "GUI.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    window.read_dir()
    assert tool.project_dir == str(tmp_path)
    assert not window.StartButton.isEnabled()

    monkeypatch.setattr(
        "GUI.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(tmp_path / "input.cst"), True),
    )
    window.read_cst()
    assert window.StartButton.isEnabled()
    window.close()


def test_selecting_cst_first_does_not_invent_project_directory(
    qapp, monkeypatch, tmp_path
):
    window, tool = make_window(qapp)
    monkeypatch.setattr(
        "GUI.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(tmp_path / "input.cst"), True),
    )

    window.read_cst()

    assert tool.cst_path == str(tmp_path / "input.cst")
    assert tool.project_dir is None
    assert not window.StartButton.isEnabled()
    window.close()


def test_buttons_stay_locked_until_background_end_signal(qapp, monkeypatch, tmp_path):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)

    window.run()
    assert window.controller.state is RunState.RUNNING
    process_until(qapp, lambda: tool.start_count == 1)
    assert not window.StartButton.isEnabled()
    assert not window.selectProjectDirButton.isEnabled()
    assert not window.CalcDialogBox.enabled
    assert not window.PPSDialogBox.enabled

    tool.run_gate.set()
    process_until(qapp, lambda: window.controller.state is RunState.READY)
    assert window.StartButton.isEnabled()
    assert window.selectProjectDirButton.isEnabled()
    assert window.CalcDialogBox.enabled
    assert window.PPSDialogBox.enabled
    process_until(qapp, lambda: window.controller._thread is None)
    window.close()


def test_worker_count_is_configurable_and_locked_during_run(
    qapp, monkeypatch, tmp_path
):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)
    window.workerCountSpinBox.setValue(3)

    window.run()
    process_until(qapp, lambda: tool.start_count == 1)

    assert tool.worker_count == 3
    assert not window.workerCountSpinBox.isEnabled()

    tool.run_gate.set()
    process_until(qapp, lambda: window.controller.state is RunState.READY)
    process_until(qapp, lambda: window.controller._thread is None)
    assert window.workerCountSpinBox.isEnabled()
    window.close()


def test_continue_and_safe_options_are_user_configurable(
    qapp, monkeypatch, tmp_path
):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)
    assert window.checkBox_CTN.isEnabled()
    assert window.checkBox_SAFE.isEnabled()
    window.checkBox_CTN.setChecked(True)
    window.checkBox_SAFE.setChecked(True)

    window.run()
    process_until(qapp, lambda: tool.start_count == 1)
    assert tool.flags == (True, True)
    tool.run_gate.set()
    process_until(qapp, lambda: not window.controller.has_active_work)
    window.close()


@pytest.mark.parametrize(("stage", "result"), [("wininit", False), ("run_info", 0)])
def test_initialization_failure_does_not_start_worker(
    qapp, monkeypatch, tmp_path, stage, result
):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)
    if stage == "wininit":
        tool.wininit_result = result
    else:
        tool.run_info_result = result

    window.run()

    process_until(qapp, lambda: window.controller.state is RunState.FAILED)
    assert tool.start_count == 0
    assert window.StartButton.isEnabled()
    process_until(qapp, lambda: window.controller._thread is None)
    window.close()


def test_cancelled_file_dialog_does_not_make_window_ready(qapp, monkeypatch):
    window, tool = make_window(qapp)
    monkeypatch.setattr(
        "GUI.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: "",
    )
    window.read_dir()
    assert tool.project_dir is None
    assert not window.StartButton.isEnabled()
    window.close()


def test_background_logging_reaches_widget_through_qt_signal(qapp):
    window, tool = make_window(qapp)
    thread = threading.Thread(target=lambda: tool.logger.info("worker-log-message"))
    thread.start()
    thread.join()
    qapp.processEvents()

    assert "worker-log-message" in window.logTextBox.widget.toPlainText()
    window.close()


def test_worker_exception_enters_failed_state_and_can_retry(
    qapp, monkeypatch, tmp_path
):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)
    tool.start_exception = RuntimeError("boom")

    window.run()
    process_until(qapp, lambda: window.controller.state is RunState.FAILED)
    process_until(qapp, lambda: window.controller._thread is None)
    assert window.StartButton.isEnabled()
    assert "boom" in window.logTextBox.widget.toPlainText()

    tool.start_exception = None
    tool.run_gate.set()
    window.run()
    process_until(qapp, lambda: window.controller.state is RunState.READY)
    process_until(qapp, lambda: window.controller._thread is None)
    assert tool.start_count == 2
    window.close()


def test_repeated_start_is_rejected_while_running(qapp, monkeypatch, tmp_path):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)

    window.run()
    window.run()
    process_until(qapp, lambda: tool.start_count == 1)
    assert window.controller.state is RunState.RUNNING

    tool.run_gate.set()
    process_until(qapp, lambda: window.controller.state is RunState.READY)
    process_until(qapp, lambda: window.controller._thread is None)
    assert tool.start_count == 1
    window.close()


def test_illegal_state_transition_is_explicit(qapp):
    window, _ = make_window(qapp)
    with pytest.raises(InvalidRunState, match="IDLE -> STOPPING"):
        window.controller._transition(RunState.STOPPING)
    window.close()


def test_stage_progress_is_reported_without_blocking_ui(
    qapp, monkeypatch, tmp_path
):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)
    stages = []
    window.controller.stage_changed.connect(stages.append)

    window.run()
    process_until(qapp, lambda: "running" in stages)
    assert stages[:3] == ["initializing", "preparing", "running"]
    assert window.statusbar.currentMessage() == "RUNNING: running"
    assert window.runProgressBar.maximum() == 4
    assert window.runProgressBar.value() == 3

    tool.run_gate.set()
    process_until(qapp, lambda: window.controller.state is RunState.READY)
    process_until(qapp, lambda: window.controller._thread is None)
    assert stages[-1] == "completed"
    assert window.runProgressBar.value() == 4
    window.close()


def test_close_while_running_requests_standard_stop_and_waits(
    qapp, monkeypatch, tmp_path
):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)
    window.run()
    process_until(qapp, lambda: tool.start_count == 1)

    event = QCloseEvent()
    window.closeEvent(event)

    assert not event.isAccepted()
    assert window.controller.state is RunState.STOPPING
    assert window._close_pending
    process_until(qapp, lambda: tool.stop_count == 1)
    process_until(qapp, lambda: not window.controller.has_active_work)
    process_until(qapp, lambda: not window._close_pending)
    assert tool.stop_count == 1


def test_repeated_close_does_not_duplicate_stop_request(
    qapp, monkeypatch, tmp_path
):
    window, tool = make_window(qapp)
    choose_inputs(window, monkeypatch, tmp_path)
    window.run()
    process_until(qapp, lambda: tool.start_count == 1)

    first = QCloseEvent()
    second = QCloseEvent()
    window.closeEvent(first)
    window.closeEvent(second)

    process_until(qapp, lambda: tool.stop_count == 1)
    process_until(qapp, lambda: not window.controller.has_active_work)
    process_until(qapp, lambda: not window._close_pending)
    assert not first.isAccepted()
    assert not second.isAccepted()
    assert tool.stop_count == 1
