import logging
import os
import threading
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget
from GUI.event_log_view import StructuredLogHandler, EventTableModel, snapshot_record


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qapp):
    app = qapp
    parent = QWidget()
    handler = StructuredLogHandler(parent)
    handler.panel.resize(1000, 600)
    handler.panel.show()
    app.processEvents()
    yield handler, app
    handler.close()
    parent.close()


def make_record(message='message', level=logging.INFO, **extras):
    record = logging.LogRecord('test', level, __file__, 42, message, (), None, 'source_function')
    record.__dict__.update(extras)
    return record


def test_filters_details_raw_and_no_clear_api(view):
    handler, app = view
    handler.emit(make_record('first task', phase='solve', task_id='A', run_id='r', artifacts={'snapshot':'copy.cst'}))
    handler.emit(make_record('second task failure', logging.ERROR, phase='shutdown', task_id='B'))
    handler.emit(make_record('debug details', logging.DEBUG))
    handler.flush_pending()
    assert handler.model.rowCount() == 3
    assert handler.proxy.rowCount() == 2
    handler.search.setText('failure')
    handler.apply_filters()
    assert handler.proxy.rowCount() == 1
    handler.table.setCurrentIndex(handler.proxy.index(0, 0))
    assert 'second task failure' in handler.details.toPlainText()
    assert 'source_function' in handler.details.toPlainText()
    assert '"task_id": "B"' in handler.details.toPlainText()
    handler.search.clear()
    handler.phase.setText('solve')
    handler.task.setText('A')
    handler.apply_filters()
    assert handler.proxy.rowCount() == 1
    handler.phase.clear()
    handler.task.clear()
    handler.level_filter.setCurrentIndex(3)
    handler.apply_filters()
    assert handler.proxy.rowCount() == 3
    handler.tabs.setCurrentIndex(1)
    assert 'debug details' in handler.widget.toPlainText()
    handler.emit(make_record('pending'))
    assert not hasattr(handler, 'clear')
    assert not hasattr(handler.model, 'clear')
    app.processEvents()
    handler.flush_pending()
    assert handler.model.rowCount() == 4
    assert 'debug details' in handler.widget.toPlainText()
    assert 'pending' in handler.widget.toPlainText()


def test_only_explicit_identified_progress_coalesces_not_errors_or_other_tasks(view):
    handler, app = view
    context = dict(event='CST_WAIT_PROGRESS', run_id='r', session_id='s', task_id='A', phase='solve')
    handler.emit(make_record('10%', **context))
    handler.emit(make_record('20%', **context))
    handler.emit(make_record('other', **{**context,'task_id':'B'}))
    handler.emit(make_record('failure', logging.ERROR, **context))
    handler.emit(make_record('failure', logging.ERROR, **context))
    handler.flush_pending()
    assert handler.model.rowCount() == 4
    assert handler.model.rows[0]['updates'] == 2
    assert handler.model.rows[0]['summary'] == '20%'
    handler.emit(make_record('30%', **context))
    handler.flush_pending()
    assert handler.model.rows[0]['updates'] == 3
    assert handler.model.rowCount() == 4


def test_exception_copy_and_original_record_are_not_mutated(view):
    handler, app = view
    try:
        raise ValueError('bad parameter')
    except ValueError:
        import sys
        record = make_record('failed', logging.ERROR, record_id='record-123', diagnostics='D:/diagnostics')
        record.exc_info = sys.exc_info()
        event = snapshot_record(record)
    assert 'ValueError: bad parameter' in event['error']
    assert not any(isinstance(value, BaseException) for value in event.values())
    handler.model.append_events([event])
    handler.table.setCurrentIndex(handler.proxy.index(0,0))
    assert 'record-123' in handler.details.toPlainText()
    assert 'D:/diagnostics' in handler.details.toPlainText()


def test_file_entry_uses_configured_handler_paths_not_guessed_paths(view, tmp_path, monkeypatch):
    handler, app = view
    logger = logging.getLogger('event-file-test')
    path = tmp_path/'application.log'
    file_handler = logging.FileHandler(path, encoding='utf-8')
    logger.addHandler(file_handler)
    opened = []
    monkeypatch.setattr('GUI.event_log_view.QDesktopServices.openUrl', lambda url:opened.append(url.toLocalFile()) or True)
    try:
        handler.bind_logger(logger)
        assert handler.log_button.isEnabled()
        handler.open_file('.log')
        assert [Path(item) for item in opened] == [path]
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()


def test_threaded_flood_has_bounded_queue_model_and_details(view):
    handler, app = view
    started = time.perf_counter()
    worker = threading.Thread(target=lambda:[handler.emit(make_record(f'row-{i}')) for i in range(20000)])
    worker.start()
    worker.join()
    assert len(handler._events) == handler.MAX_PENDING
    while handler._events:
        handler.flush_pending()
        app.processEvents()
    assert handler.model.rowCount() == handler.MAX_PENDING
    assert handler.model.rows[-1]['summary'] == 'row-19999'
    assert '18000' in handler.notice.text()
    handler.model.LIMIT = 100
    handler.emit(make_record('very long' * 10000))
    handler.flush_pending()
    assert handler.model.rowCount() == 100
    assert handler.model.rows[-1]['clipped']
    print(f'20000 structured records enqueue+drain: {time.perf_counter()-started:.3f}s offscreen')


def test_dragging_and_selection_pause_follow_and_latest_resumes(view):
    handler, app = view
    for i in range(200):
        handler.emit(make_record(f'event-{i}'))
    while handler._events:
        handler.flush_pending()
    app.processEvents()
    scroll = handler.table.verticalScrollBar()
    handler.table.setCurrentIndex(handler.proxy.index(10,0))
    selected = handler.details.toPlainText()
    handler.emit(make_record('new-event'))
    scroll.setSliderDown(True)
    handler.flush_pending()
    assert len(handler._events) == 1
    scroll.setSliderDown(False)
    handler.flush_pending()
    assert handler.details.toPlainText() == selected
    handler.latest.click()
    assert not handler.table.currentIndex().isValid()
    assert scroll.value() == scroll.maximum()
