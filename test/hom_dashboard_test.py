import json
from pathlib import Path

from PyQt5.QtCore import Qt
from GUI.hom_dashboard import HomDisplayReader, HomDashboard
from test.gui_main_window_test import qapp, make_window, accept_confirmation


def checkpoint(project, *, modes=2):
    path = project / 'save/csv/hom_scan_checkpoint.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'policy': {'start': 500, 'stop': 1000},
        'coverage': {'confirmed_frontier': 700, 'calculated_upper': 750},
        'pending': [{'lo': 700, 'hi': 750}],
        'report': {'failed': [], 'modes': [{'mode_index': 1, 'frequency': 600 + i,
            'values': {'R/Q_x': 2 + i, 'Q': 1000 + i}, 'task_id': f'task-{i}'} for i in range(modes)]}}))
    return path


def test_reader_caches_by_project_and_stat_and_does_not_write(tmp_path, monkeypatch):
    path = checkpoint(tmp_path)
    original = path.read_bytes()
    reader = HomDisplayReader()
    first = reader.read(tmp_path)
    assert first['available'] and first['total_modes'] == 2
    import GUI.hom_dashboard as module
    def no_parse(*args):
        raise AssertionError('unchanged file should not be parsed')
    monkeypatch.setattr(module.json, 'loads', no_parse)
    assert reader.read(tmp_path) is first
    assert path.read_bytes() == original


def test_reader_missing_corrupt_and_oversize_are_not_fake_results(tmp_path):
    reader = HomDisplayReader()
    assert not reader.read(tmp_path)['available']
    path = checkpoint(tmp_path)
    path.write_text('{broken')
    bad = reader.read(tmp_path)
    assert not bad['available'] and bad['diagnostic']
    assert str(path) not in bad['reason']
    with path.open('wb') as stream:
        stream.seek(17 * 1024**2)
        stream.write(b'x')
    assert '16MiB' in reader.read(tmp_path)['diagnostic']


def test_primary_results_use_coverage_not_highest_mode_or_local_percentage(qapp, tmp_path):
    checkpoint(tmp_path)
    display = HomDisplayReader().read(tmp_path)
    panel = HomDashboard()
    status = {'project': str(tmp_path), 'mode_count': 2, 'hom_display': display}
    panel.update_snapshot(status)
    assert panel.model.rowCount() == 2
    assert panel.coverageBar.value() == 400  # (700-500)/(1000-500), not highest mode 601.
    assert panel.model.data(panel.model.index(0, 1)) == '600'
    assert 'R/Q_x' in panel.model.metrics
    assert panel.model.data(panel.model.index(0, 3)) == '2'
    assert '750 MHz' in panel.coverage.text()
    resets = []
    panel.model.modelReset.connect(lambda: resets.append(True))
    panel.update_snapshot(status)
    assert not resets
    panel.update_snapshot({'project': 'other', 'mode_count': 0})
    assert panel.model.rowCount() == 0 and panel.coverageBar.value() == 0


def test_view_defaults_to_results_and_keeps_full_logs_in_details(qapp):
    window, _ = make_window(qapp)
    window.show()
    qapp.processEvents()
    assert window.resultTabs.currentIndex() == 0
    assert not window.runSummaryFrame.isVisible()
    assert not window.logTextBox.panel.isVisible()
    assert window.homDashboard.isVisible()
    assert window.logTextBox.export_button.isVisible()
    window.resultTabs.setCurrentIndex(1)
    assert window.runSummaryFrame.isVisible()
    assert window.logTextBox.panel.isVisible()
    window.close()


def test_main_error_summary_omits_trace_but_retains_full_log(qapp):
    window, _ = make_window(qapp)
    window.onRunError('求解失败\n源码：private/file.py:12\nManager internal details')
    assert '求解失败' in window.stateDetailLabel.text()
    assert 'Manager' not in window.stateDetailLabel.text()
    window.logTextBox.flush_pending()
    assert any('Manager internal details' in row['message'] for row in window.logTextBox.model.rows)
    window.close()


def test_result_read_error_and_old_result_are_explicit(qapp, tmp_path):
    checkpoint(tmp_path)
    panel = HomDashboard()
    reader = HomDisplayReader()
    panel.update_snapshot({'project': str(tmp_path), 'hom_display': reader.read(tmp_path)})
    checkpoint(tmp_path).write_text('{bad')
    panel.update_snapshot({'project': str(tmp_path), 'hom_display': reader.read(tmp_path)})
    assert panel.model.rowCount() == 2
    assert '历史结果' in panel.notice.text()


def test_reader_display_limit_does_not_alter_checkpoint(qapp, tmp_path):
    path = checkpoint(tmp_path, modes=5002)
    reader = HomDisplayReader()
    value = reader.read(tmp_path)
    assert value['total_modes'] == 5002 and len(value['modes']) == 5000
    panel = HomDashboard()
    panel.update_snapshot({'project': str(tmp_path), 'hom_display': value})
    assert '最近5000' in panel.notice.text()
    assert panel.model.data(panel.model.index(0, 0)) == '3'
    assert len(json.loads(path.read_text())['report']['modes']) == 5002


def test_client_observation_reads_results_without_starting_a_job(qapp, tmp_path):
    from GUI.runner_controller import RunnerController
    from GUI.runner_backend import RunnerBackend
    from GUI.application_service import ConfigurationService
    from test.gui_runner_test import Client
    checkpoint(tmp_path)
    backend = RunnerBackend()
    backend.project = str(tmp_path)
    backend.client = Client(str(tmp_path))
    controller = RunnerController(ConfigurationService(backend))
    controller.timer.stop()
    try:
        status, events = controller.pool.submit(controller._observe, backend.client).result(timeout=5)
        assert status['hom_display']['total_modes'] == 2
        assert not backend.client.ops  # Read/display only, no start/recover commands.
    finally:
        controller.backend.client = None
        controller.detach()


def test_project_selection_clears_old_results_and_cancel_keeps_selection(qapp, tmp_path, monkeypatch):
    window, _ = make_window(qapp)
    checkpoint(tmp_path)
    window.renderRunnerSnapshot({'project': str(tmp_path), 'hom_display': HomDisplayReader().read(tmp_path)})
    assert window.homDashboard.model.rowCount() == 2
    other = tmp_path / 'other'
    other.mkdir()
    monkeypatch.setattr('GUI.main_window.QFileDialog.getExistingDirectory', lambda *a: str(other))
    window.read_dir()
    assert window.homDashboard.model.rowCount() == 0
    monkeypatch.setattr('GUI.main_window.QFileDialog.getExistingDirectory', lambda *a: '')
    window.read_dir()
    assert window.uiProjectDir == str(other)
    window.close()
