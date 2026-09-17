from __future__ import annotations

from collections import deque
import logging
import os
from pathlib import Path
from threading import Event, Lock
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication

from GUI.mymainwindow import mywindow
from GUI.run_controller import RunState
from csttool.cstmanager import CSTManager, ManagerState, SimulationTask


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


class FakeGlobalConfig:
    def __init__(self, root: Path):
        self.conf = {
            "BASE": {"datadir": str(root / "data")},
            "CST": {"cstexepath": str(root / "fake-cst.exe")},
        }


class FakeProjectConfig:
    def __init__(self, root: Path, pps):
        self.currProjectDir = root
        self.conf = {
            "DIRS": {"tempdir": "temp", "resultdir": "result"},
            "CST": {"CSTFilename": "input.cst"},
            "PROJECT": {"ProjectType": "fake-gui"},
        }
        self._pps = pps

    def getCurrPPSList(self):
        return list(self._pps)


class FlowFakeWorker:
    def __init__(self, worker_id, tracker, outcomes, release: Event):
        self.ID = worker_id
        self._tracker = tracker
        self._outcomes = outcomes
        self._release = release
        self.stopped = False

    def runWithParam(self, resultname, *, params):
        with self._tracker["lock"]:
            self._tracker["calls"].append((resultname, dict(params)))
            self._tracker["active"] += 1
            self._tracker["peak"] = max(
                self._tracker["peak"], self._tracker["active"]
            )
        try:
            assert self._release.wait(5), "fake CST worker was not released"
            time.sleep(0.02)
            outcome = self._outcomes.popleft() if self._outcomes else "Success"
            return {
                "TaskStatus": outcome,
                "RunName": resultname,
                "RunParameters": dict(params),
                "PostProcessResult": {"worker": self.ID},
            }
        finally:
            with self._tracker["lock"]:
                self._tracker["active"] -= 1

    def stop(self):
        self.stopped = True
        self._release.set()


class FakeWorkerGuiBackend:
    def __init__(self, root: Path, *, outcomes=(), blocked=False):
        self.logger = logging.getLogger(f"gui-fake-worker-{id(self)}")
        self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG)
        self.root = root
        self.project_dir = None
        self.cst_path = None
        self.flags = None
        self.pps = []
        self.alg_attrs = {"fmin": 720, "fmax": 880}
        self.outcomes = deque(outcomes)
        self.release = Event()
        if not blocked:
            self.release.set()
        self.tracker = {"lock": Lock(), "calls": [], "active": 0, "peak": 0}
        self.workers = []
        self.manager = None
        self.results = []
        self.worker_count = 2

    def setProjectDir(self, path):
        self.project_dir = path

    def setCSTFilePath(self, path):
        self.cst_path = path

    def getCurrPostProcessList(self):
        return list(self.pps)

    def setCurrPostProcessList(self, values):
        self.pps = list(values)

    def getAlgAttrs(self):
        return dict(self.alg_attrs)

    def setAlgAttrs(self, values):
        self.alg_attrs = dict(values)

    def setFlags(self, start_from_existing, safe):
        self.flags = (start_from_existing, safe)

    def setWorkerCount(self, worker_count):
        self.worker_count = int(worker_count)

    def wininit(self):
        return bool(self.project_dir and self.cst_path)

    def setRunInfos(self):
        root = Path(self.project_dir)

        def worker_factory(worker_id, config, logger):
            worker = FlowFakeWorker(
                worker_id, self.tracker, self.outcomes, self.release
            )
            self.workers.append(worker)
            return worker

        self.manager = CSTManager(
            FakeGlobalConfig(root),
            FakeProjectConfig(root, self.pps),
            params=["fmin", "fmax"],
            logger=self.logger,
            maxTask=self.worker_count,
            worker_factory=worker_factory,
        )

    def starttask(self):
        tasks = [
            SimulationTask({"fmin": 720, "fmax": 800}, "band-1"),
            SimulationTask({"fmin": 800, "fmax": 880}, "band-2"),
        ]
        try:
            self.results = self.manager.run_batch(tasks)
            if len(self.results) != len(tasks):
                raise RuntimeError("fake worker batch ended without all results")
            failures = [
                item for item in self.results if item["TaskStatus"] != "Success"
            ]
            if failures:
                raise RuntimeError("fake worker returned task failure")
        finally:
            self.manager.stop()

    def request_stop(self):
        if self.manager is not None:
            self.manager.stop()


def process_until(qapp, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("fake-worker GUI condition timed out")


def make_window(qapp, tmp_path, monkeypatch, **backend_options):
    backend = FakeWorkerGuiBackend(tmp_path, **backend_options)
    window = mywindow(backend, FakeDialog(), FakeDialog())
    cst_path = tmp_path / "input.cst"
    cst_path.write_bytes(b"fake project")
    monkeypatch.setattr(
        "GUI.mymainwindow.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        "GUI.mymainwindow.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(cst_path), True),
    )
    window.selectProjectDirButton.click()
    window.selectCSTPathButton.click()
    assert window.controller.state is RunState.READY
    return window, backend


def test_gui_success_flow_uses_real_manager_with_fake_workers(
    qapp, tmp_path, monkeypatch
):
    window, backend = make_window(qapp, tmp_path, monkeypatch)

    window.StartButton.click()
    process_until(qapp, lambda: window.controller.state is RunState.READY)
    process_until(qapp, lambda: not window.controller.has_active_work)

    assert [item["RunName"] for item in backend.results] == ["band-1", "band-2"]
    assert backend.tracker["peak"] == 2
    assert backend.manager.state is ManagerState.CLOSED
    assert all(worker.stopped for worker in backend.workers)
    assert window.runProgressBar.value() == 4
    window.close()


def test_gui_selected_worker_count_controls_real_manager_pool(
    qapp, tmp_path, monkeypatch
):
    window, backend = make_window(qapp, tmp_path, monkeypatch)
    window.workerCountSpinBox.setValue(1)

    window.StartButton.click()
    process_until(qapp, lambda: window.controller.state is RunState.READY)
    process_until(qapp, lambda: not window.controller.has_active_work)

    assert backend.worker_count == 1
    assert len(backend.workers) == 1
    assert backend.tracker["peak"] == 1
    window.close()


def test_gui_failure_flow_surfaces_fake_worker_failure(
    qapp, tmp_path, monkeypatch
):
    window, backend = make_window(
        qapp, tmp_path, monkeypatch, outcomes=("Failure", "Success")
    )

    window.StartButton.click()
    process_until(qapp, lambda: window.controller.state is RunState.FAILED)
    process_until(qapp, lambda: not window.controller.has_active_work)

    assert "fake worker returned task failure" in window.logTextBox.widget.toPlainText()
    assert backend.manager.state is ManagerState.CLOSED
    assert window.StartButton.isEnabled()
    window.close()


def test_gui_close_flow_stops_real_manager_and_fake_workers(
    qapp, tmp_path, monkeypatch
):
    window, backend = make_window(qapp, tmp_path, monkeypatch, blocked=True)
    window.StartButton.click()
    process_until(qapp, lambda: backend.tracker["active"] > 0)

    event = QCloseEvent()
    window.closeEvent(event)

    assert not event.isAccepted()
    assert window.controller.state is RunState.STOPPING
    process_until(qapp, lambda: not window.controller.has_active_work)
    process_until(qapp, lambda: not window._close_pending)
    assert backend.manager.state is ManagerState.CLOSED
    assert all(worker.stopped for worker in backend.workers)
