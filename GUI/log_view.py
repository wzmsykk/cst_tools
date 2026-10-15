"""Bounded, batched GUI mirror of the full file log."""
from collections import deque
import logging
import threading

from PyQt5.QtCore import QObject, QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QPlainTextEdit


class _Wakeup(QObject):
    ready = pyqtSignal()


class QPlainTextEditLogger(logging.Handler):
    MAX_PENDING = 2000
    MAX_RECORD_CHARS = 4096
    BATCH_SIZE = 128
    MAX_BLOCKS = 5000

    def __init__(self, parent):
        super().__init__()
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)
        self.widget.setUndoRedoEnabled(False)
        self.widget.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.widget.setMaximumBlockCount(self.MAX_BLOCKS)
        self.widget.setToolTip("仅显示最近5000行；长消息界面截断，完整内容见文件日志。开启自动滚动时，向上阅读暂停跟随，回到底部恢复。")
        self._pending = deque()
        self._guard = threading.Lock()
        self._scheduled = False
        self._disposed = False
        self._dropped = 0
        self.auto_scroll = True
        self._wakeup = _Wakeup(parent)
        self._wakeup.ready.connect(self.flush_pending, Qt.QueuedConnection)
        self._timer = QTimer(self.widget)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self.flush_pending)
        self.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            message = self.format(record)
            if len(message) > self.MAX_RECORD_CHARS:
                message = message[:self.MAX_RECORD_CHARS] + " …[界面截断，完整内容见文件日志]"
            with self._guard:
                if self._disposed:
                    return
                if len(self._pending) >= self.MAX_PENDING:
                    self._pending.popleft()
                    self._dropped += 1
                self._pending.append(message)
                wake = not self._scheduled
                self._scheduled = True
            if wake:
                self._wakeup.ready.emit()
        except Exception:
            self.handleError(record)

    def flush_pending(self):
        """GUI thread only; yield between bounded batches and during dragging."""
        if self._disposed:
            return
        scroll = self.widget.verticalScrollBar()
        if scroll.isSliderDown():
            self._timer.start()
            return
        with self._guard:
            if self._disposed:
                self._timer.stop()
                return
            batch = [self._pending.popleft() for _ in range(min(self.BATCH_SIZE, len(self._pending)))]
            dropped, self._dropped = self._dropped, 0
            more = bool(self._pending)
            self._scheduled = more
        if dropped:
            batch.insert(0, f"[界面日志积压：省略{dropped}条显示，完整内容见文件日志]")
        if batch:
            follow = self.auto_scroll and scroll.value() >= scroll.maximum() - 1
            first = self.widget.firstVisibleBlock().blockNumber()
            before = self.widget.document().blockCount()
            removed = max(0, before + sum(text.count('\n') + 1 for text in batch) - self.MAX_BLOCKS)
            self.widget.appendPlainText('\n'.join(batch))
            if follow:
                scroll.setValue(scroll.maximum())
            else:
                scroll.setValue(max(0, first - removed))
        if more:
            self._timer.start()
        else:
            self._timer.stop()

    def set_auto_scroll(self, enabled):
        """GUI-thread display preference; never changes log intake or storage."""
        self.auto_scroll = bool(enabled)
        if self.auto_scroll:
            self.widget.verticalScrollBar().setValue(self.widget.verticalScrollBar().maximum())

    def close(self):
        with self._guard:
            self._disposed = True
            self._pending.clear()
        try:
            if QThread.currentThread() == self._timer.thread():
                self._timer.stop()
        except RuntimeError:
            pass  # Parent already destroyed; logging.shutdown may close again.
        # Queued GUI callbacks will observe disposed; no worker touches QWidget.
        super().close()
