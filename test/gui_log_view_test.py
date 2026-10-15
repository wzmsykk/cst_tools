import logging
import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication, QWidget, QPlainTextEdit
from GUI.log_view import QPlainTextEditLogger


@pytest.fixture
def view():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    handler = QPlainTextEditLogger(parent)
    handler.widget.resize(600, 240)
    handler.widget.show()
    app.processEvents()
    yield handler, app
    handler.close()
    parent.close()


def record(text):
    return logging.LogRecord('test', logging.INFO, __file__, 1, text, (), None)


def test_flood_is_bounded_and_coalesces_wakeup(view):
    handler, app = view
    spy = QSignalSpy(handler._wakeup.ready)
    started = time.perf_counter()
    thread = threading.Thread(target=lambda:[handler.emit(record(f'line-{i}')) for i in range(20000)])
    thread.start()
    thread.join()
    assert len(spy) == 1
    assert len(handler._pending) == handler.MAX_PENDING
    while handler._pending:
        handler.flush_pending()
        app.processEvents()
    assert '省略18000条' in handler.widget.toPlainText()
    assert 'line-19999' in handler.widget.toPlainText()
    assert handler.widget.document().blockCount() <= handler.MAX_BLOCKS
    print(f'GUI flood 20000 records enqueue+drain: {time.perf_counter()-started:.3f}s (offscreen)')


def test_scroll_back_drag_and_tail_follow(view):
    handler, app = view
    handler.widget.setPlainText('\n'.join(str(i) for i in range(1000)))
    app.processEvents()
    scroll = handler.widget.verticalScrollBar()
    scroll.setValue(100)
    first = handler.widget.firstVisibleBlock().text()
    handler.emit(record('new tail'))
    handler.flush_pending()
    assert handler.widget.firstVisibleBlock().text() == first
    scroll.setSliderDown(True)
    handler.emit(record('during drag'))
    handler.flush_pending()
    assert 'during drag' not in handler.widget.toPlainText()
    scroll.setSliderDown(False)
    scroll.setValue(scroll.maximum())
    handler.flush_pending()
    assert 'during drag' in handler.widget.toPlainText()
    assert scroll.value() == scroll.maximum()


def test_no_clear_api_and_long_records_are_display_only_truncated(view):
    handler, app = view
    text = 'x' * 100000
    item = record(text)
    handler.emit(item)
    handler.flush_pending()
    assert len(handler.widget.toPlainText()) < 5000
    assert '界面截断' in handler.widget.toPlainText()
    assert item.msg == text
    assert handler.widget.lineWrapMode() == QPlainTextEdit.NoWrap
    handler.emit(record('pending'))
    assert not hasattr(handler, 'clear')
    app.processEvents()
    handler.flush_pending()
    assert 'pending' in handler.widget.toPlainText()
    assert '界面截断' in handler.widget.toPlainText()
    handler.close()
    handler.emit(record('after close'))
    assert not handler._pending


def test_document_eviction_keeps_visible_anchor_when_available(view):
    handler, app = view
    handler.widget.setPlainText('\n'.join(str(i) for i in range(handler.MAX_BLOCKS)))
    app.processEvents()
    handler.widget.verticalScrollBar().setValue(100)
    anchor = handler.widget.firstVisibleBlock().text()
    for i in range(20):
        handler.emit(record(f'new-{i}'))
    handler.flush_pending()
    assert handler.widget.document().blockCount() == handler.MAX_BLOCKS
    assert handler.widget.firstVisibleBlock().text() == anchor


def test_auto_scroll_defaults_on_and_off_keeps_position_while_receiving(view):
    handler, app = view
    assert handler.auto_scroll
    handler.widget.setPlainText('\n'.join(str(i) for i in range(300)))
    app.processEvents()
    handler.set_auto_scroll(True)
    scroll = handler.widget.verticalScrollBar()
    assert scroll.value() == scroll.maximum()
    handler.set_auto_scroll(False)
    previous = scroll.value()
    for i in range(20):
        handler.emit(record(f'new-{i}'))
    handler.flush_pending()
    app.processEvents()
    assert scroll.value() == previous
    assert 'new-19' in handler.widget.toPlainText()
    handler.set_auto_scroll(True)
    assert scroll.value() == scroll.maximum()
