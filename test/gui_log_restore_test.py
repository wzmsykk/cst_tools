"""Durable GUI history/status restoration, no CST or automatic computation."""
import json
from pathlib import Path

from GUI.main_window import MainWindow
from GUI.runner_backend import RunnerBackend
from csttool.runner import Runner
from test.gui_runner_test import app, Client, wait
from test.runner_test import WaitingExecution, fake_runner


def write_log(directory, message, timestamp='2026-10-15T01:02:03+00:00'):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'application.jsonl').write_text(json.dumps(dict(
        timestamp=timestamp, level='INFO', message=message,
        context={'run_id': message}, source={'file': 'original.py', 'line': 12, 'function': 'solve'})) + '\n', encoding='utf-8')


def test_runner_restart_keeps_history_and_task_status(tmp_path):
    first = tmp_path / 'logs/first'
    second = tmp_path / 'logs/second'
    write_log(first, 'first run')
    write_log(second, 'second run')
    runner = Runner(tmp_path, WaitingExecution)
    runner.update(log_directory=str(first), run_id='first', state='COMPLETED', phase='completed')
    runner.update(log_directory=None, run_id='second')
    runner.update(log_directory=str(second), state='INTERRUPTED', phase='interrupted',
        coverage={'confirmed_frontier': 720.5}, mode_count=3, completed_tasks=2,
        total_tasks=4, session_safety='confirmed-closed')
    runner.close()
    restored = Runner(tmp_path, WaitingExecution)
    try:
        status = restored.snapshot()
        assert status['state'] == 'INTERRUPTED'
        assert status['coverage']['confirmed_frontier'] == 720.5
        assert status['completed_tasks'] == 2 and status['total_tasks'] == 4
        assert status['mode_count'] == 3
        assert status['log_directory'] == str(second)
        cursor, events = 0, []
        for _ in range(4):
            response = restored.events(cursor)
            events.extend(response['events'])
            cursor = response['cursor']
        assert [e['message'] for e in events] == ['first run', 'second run']
        assert restored.worker is None
    finally:
        restored.close()


def test_pre_runner_project_discovers_logs_and_checkpoint_without_running(tmp_path):
    from csttool.configuration import write_json_atomic
    directory = tmp_path / 'logs/legacy'
    write_log(directory, 'legacy project')
    write_json_atomic(tmp_path / 'save/csv/hom_scan_checkpoint.json',
        {'coverage': {'confirmed_frontier': 650}, 'report': {'modes': [{}, {}]}})
    runner = Runner(tmp_path, WaitingExecution)
    try:
        assert runner.events()['events'][0]['message'] == 'legacy project'
        assert runner.snapshot()['mode_count'] == 2
        assert runner.snapshot()['coverage']['confirmed_frontier'] == 650
        assert runner.worker is None
    finally:
        runner.close()


def test_new_run_keeps_existing_cursor_without_replaying_old_history(tmp_path):
    runner = Runner(tmp_path, WaitingExecution)
    first, second = tmp_path / 'logs/first', tmp_path / 'logs/second'
    write_log(first, 'before')
    write_log(second, 'after')
    try:
        runner.update(log_directory=str(first))
        previous = runner.events()
        assert previous['events'][0]['message'] == 'before'
        runner.update(log_directory=None)
        gap = runner.events(previous['cursor'])
        assert not gap['events']
        assert gap['cursor']['source'] == previous['cursor']['source']
        runner.update(log_directory=str(second))
        transition = runner.events(previous['cursor'])
        assert not transition['events']
        current = runner.events(transition['cursor'])
        assert [event['message'] for event in current['events']] == ['after']
        # Starting a fresh observer replays both sources in order.
        assert runner.events()['events'][0]['message'] == 'before'
    finally:
        runner.close()


def test_missing_or_partial_old_history_does_not_block_current_log(tmp_path):
    runner = Runner(tmp_path, WaitingExecution)
    first, second = tmp_path / 'logs/first', tmp_path / 'logs/second'
    first.mkdir(parents=True)
    (first / 'application.jsonl').write_bytes(b'{"partial":')
    write_log(second, 'current')
    try:
        runner.update(log_directory=str(first))
        runner.update(log_directory=str(second))
        response = runner.events()
        assert '尾行未写完' in response['events'][0]['message']
        assert runner.events(response['cursor'])['events'][0]['message'] == 'current'
        (first / 'application.jsonl').unlink()
        response = runner.events()
        assert runner.events(response['cursor'])['events'][0]['message'] == 'current'
    finally:
        runner.close()


def test_gui_reopen_loads_logs_timestamps_and_checkpoint_summary_without_start(app, tmp_path, monkeypatch):
    directory = tmp_path / 'logs/previous'
    write_log(directory, 'saved event')
    runner = Runner(tmp_path, WaitingExecution)
    runner.update(log_directory=str(directory), run_id='saved-run', state='INTERRUPTED',
        phase='interrupted', coverage={'confirmed_frontier': 812.5}, mode_count=4)
    class DirectClient(Client):
        client_id = 'gui-history-test'
        def connect(self, **kwargs):
            return runner.snapshot()
        def events(self, cursor=0):
            return runner.events(cursor)
    backend = RunnerBackend()
    backend.project = str(tmp_path)
    backend.supports_cst_backend_selection = False
    client = backend.client = DirectClient(backend.project)
    window = MainWindow(engine=backend)
    window.controller.timer.setInterval(10)
    monkeypatch.setattr(window, '_runner_close_choice', lambda: 'detach')
    try:
        window.logger.info('current GUI event')
        def restored():
            window.logTextBox.flush_pending()
            return any(row['message'] == 'saved event' for row in window.logTextBox.model.rows)
        wait(app, restored)
        rows = window.logTextBox.model.rows
        assert any(row['message'] == 'current GUI event' for row in rows)
        old = next(row for row in rows if row['message'] == 'saved event')
        assert 'original.py:12 (solve)' == old['source']
        from datetime import datetime
        assert old['time'] == datetime.fromisoformat('2026-10-15T01:02:03+00:00').astimezone().strftime('%H:%M:%S')
        assert '812.5 MHz' in window.stateDetailLabel.text()
        assert '4 个模式' in window.stateDetailLabel.text()
        assert backend.runner_status['run_id'] == 'saved-run'
        assert 'start' not in client.ops
        assert not hasattr(window, 'clearLogButton')
        assert not hasattr(window.logTextBox, 'clear')
    finally:
        window.close()
        # Qt/test teardown can deliver a second close on a detached window.
        from PyQt5.QtGui import QCloseEvent
        repeated = QCloseEvent()
        window.closeEvent(repeated)
        assert repeated.isAccepted()
        window.controller.detach()
        window.controller.pool.shutdown(wait=True)
        runner.close()


def test_unreadable_history_does_not_make_computation_unknown(tmp_path, monkeypatch):
    directory = tmp_path / 'logs/old'
    write_log(directory, 'saved')
    runner = Runner(tmp_path, WaitingExecution)
    runner.update(log_directory=str(directory), state='COMPLETED')
    original = Path.open
    def denied(path, *args, **kwargs):
        if path.name == 'application.jsonl':
            raise PermissionError('injected log-only read failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', denied)
    try:
        first = runner.events()
        assert '任务状态不受影响' in first['events'][0]['message']
        assert not runner.events(first['cursor'])['events']
        assert runner.snapshot()['state'] == 'COMPLETED'
        monkeypatch.setattr(Path, 'open', original)
        assert runner.events(first['cursor'])['events'][0]['message'] == 'saved'
    finally:
        runner.close()


def test_history_source_cursor_roundtrips_real_http(fake_runner):
    client, process = fake_runner
    directory = client.project / 'control'
    write_log(directory, 'first HTTP event')
    first = client.events()
    assert first['events'][0]['message'] == 'first HTTP event'
    assert first['cursor']['source'].endswith('application.jsonl')
    with (directory / 'application.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'level': 'INFO', 'message': 'second HTTP event'}) + '\n')
    second = client.events(first['cursor'])
    assert [event['message'] for event in second['events']] == ['second HTTP event']
    assert client.status()['state'] == 'IDLE'
