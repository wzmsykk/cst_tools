import time
from threading import Event

from PyQt5.QtGui import QCloseEvent
from test.gui_main_window_test import qapp, make_window, accept_confirmation


def until(qapp, predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline
        qapp.processEvents()
        time.sleep(0.005)
    qapp.processEvents()


def test_gui_one_click_exports_offline_project(qapp, tmp_path):
    window, _ = make_window(qapp)
    window.uiProjectDir = str(tmp_path)
    window.logTextBox.export_button.click()
    assert not window.logTextBox.export_button.isEnabled()
    until(qapp, lambda: window._diagnostic_thread is None)
    assert len(list((tmp_path / 'diagnostics').glob('*.zip'))) == 1
    assert window.logTextBox.export_button.isEnabled()
    assert '已导出' in window.stateDetailLabel.text()
    window.close()


def test_export_failure_reenables_button_and_does_not_exit(qapp, tmp_path, monkeypatch):
    import GUI.diagnostic_export as module
    def failed(project):
        raise OSError('disk full')
    monkeypatch.setattr(module, 'export_failure_bundle', failed)
    window, _ = make_window(qapp)
    window.uiProjectDir = str(tmp_path)
    window.exportFailureLogs()
    until(qapp, lambda: window._diagnostic_thread is None)
    assert window.logTextBox.export_button.isEnabled()
    assert 'disk full' in window.stateDetailLabel.text()
    window.close()


def test_export_is_nonblocking_and_close_preserves_thread(qapp, tmp_path, monkeypatch):
    import GUI.diagnostic_export as module
    release = Event()
    def blocked(project):
        assert release.wait(3)
        return {'path': str(tmp_path / 'evidence.zip'), 'files': 1, 'warnings': 0}
    monkeypatch.setattr(module, 'export_failure_bundle', blocked)
    window, _ = make_window(qapp)
    window.uiProjectDir = str(tmp_path)
    try:
        window.exportFailureLogs()
        thread = window._diagnostic_thread
        window.exportFailureLogs()
        assert window._diagnostic_thread is thread
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()
        qapp.processEvents()
    finally:
        release.set()
        until(qapp, lambda: window._diagnostic_thread is None)
        window.close()
