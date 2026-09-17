import logging
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from GUI.mymainwindow import cst_tools_main_qt, mywindow


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


class FakeMainTool(QObject):
    _signal_start = pyqtSignal()
    _signal_end = pyqtSignal()
    _signal_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"gui-p0-{id(self)}")
        self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG)
        self.project_dir = None
        self.cst_path = None
        self.start_count = 0
        self.wininit_result = True
        self.run_info_result = None

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

    def wininit(self):
        return self.wininit_result

    def setRunInfos(self):
        return self.run_info_result

    def start(self):
        self.start_count += 1
        self._signal_start.emit()

    def finish(self):
        self._signal_end.emit()

    def setAlgAttrs(self, values):
        self.alg_values = values

    def setCurrPostProcessList(self, values):
        self.pps_values = values


def make_window(qapp):
    tool = FakeMainTool()
    window = mywindow(tool, FakeDialog(), FakeDialog())
    return window, tool


def choose_inputs(window, monkeypatch, tmp_path):
    project_dir = str(tmp_path)
    cst_path = str(tmp_path / "input.cst")
    monkeypatch.setattr(
        "GUI.mymainwindow.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: project_dir,
    )
    monkeypatch.setattr(
        "GUI.mymainwindow.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (cst_path, True),
    )
    window.read_dir()
    window.read_cst()


def test_start_requires_both_project_directory_and_cst_file(qapp, monkeypatch, tmp_path):
    window, tool = make_window(qapp)
    assert not window.StartButton.isEnabled()

    monkeypatch.setattr(
        "GUI.mymainwindow.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    window.read_dir()
    assert tool.project_dir == str(tmp_path)
    assert not window.StartButton.isEnabled()

    monkeypatch.setattr(
        "GUI.mymainwindow.QFileDialog.getOpenFileName",
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
        "GUI.mymainwindow.QFileDialog.getOpenFileName",
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
    assert tool.start_count == 1
    assert not window.StartButton.isEnabled()
    assert not window.selectProjectDirButton.isEnabled()

    tool.finish()
    qapp.processEvents()
    assert window.StartButton.isEnabled()
    assert window.selectProjectDirButton.isEnabled()
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

    assert tool.start_count == 0
    assert window.StartButton.isEnabled()
    window.close()


def test_cancelled_file_dialog_does_not_make_window_ready(qapp, monkeypatch):
    window, tool = make_window(qapp)
    monkeypatch.setattr(
        "GUI.mymainwindow.QFileDialog.getExistingDirectory",
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


def test_worker_exception_always_emits_error_and_end(qapp, monkeypatch):
    def fake_init(worker):
        worker.logger = logging.getLogger(f"gui-worker-{id(worker)}")
        worker.logger.handlers.clear()
        worker.logger.addHandler(logging.NullHandler())

    monkeypatch.setattr("base.cst_tools_main.__init__", fake_init)
    worker = cst_tools_main_qt()
    worker.starttask = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    errors = []
    ended = []
    worker._signal_error.connect(errors.append)
    worker._signal_end.connect(lambda: ended.append(True))

    worker.start()
    assert worker.wait(3000)
    qapp.processEvents()

    assert errors == ["boom"]
    assert ended == [True]
